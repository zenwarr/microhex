import threading
import queue
import copy
import logging
import time
import itertools
from PyQt4.QtCore import QObject, pyqtSignal, Qt, QEvent, QSize, QAbstractListModel, QAbstractTableModel, QModelIndex
from PyQt4.QtGui import QWidget, QPushButton, QToolButton, QProgressBar, QHBoxLayout, QLabel, QMessageBox, qApp, \
                        QListView, QDialogButtonBox, QVBoxLayout, QTreeView, QItemDelegate, QStyleOptionProgressBarV2, \
                        QStyle
import hex.utils as utils
import hex.settings as settings
import hex.appsettings as appsettings


class OperationError(Exception):
    pass


class OperationState:
    # values for OperationState.status
    NotStarted, WaitingForStart, Running, Paused, Cancelled, Completed, Failed = range(7)

    _map_status = {
        NotStarted: utils.tr('Not started'),
        WaitingForStart: utils.tr('Waiting for start'),
        Running: utils.tr('Running'),
        Paused: utils.tr('Paused'),
        Cancelled: utils.tr('Cancelled'),
        Completed: utils.tr('Completed'),
        Failed: utils.tr('Failed')
    }

    def __init__(self):
        self.title = ''
        self.status = self.NotStarted
        self.progress = 0.0
        self.progressText = ''
        self.canPause = False
        self.canCancel = False
        self.messages = []  # each item is tuple - (text, level). Level is one of logging module
                            # level constants.
        self.results = {}
        self.errorCount = 0
        self.warningCount = 0

    @property
    def statusText(self):
        """Text representation of OperationState.status
        """
        return self._map_status.get(self.status, utils.tr('Unknown'))

    @property
    def isRunning(self):
        """Indicates that operation is Running. In difference from status == OperationState.Running this
        property is True when operation was started and not finished yet (status is OperationState.Running
        or OperationState.Paused).
        """
        return self.status in (self.Running, self.Paused)

    @property
    def isFinished(self):
        """Indicates that operation is finished. Returns true if status is OperationState.Completed, OperationState.Failed or
        OperationState.Cancelled
        """
        return self.status in (OperationState.Cancelled, OperationState.Completed, OperationState.Failed)

    @property
    def isStarted(self):
        return self.status not in (self.NotStarted, self.WaitingForStart)

    def __deepcopy__(self, memo):
        c = OperationState()
        c.title, c.status, c.progress, c.progressText, c.canPause, c.canCancel, c.errorCount, c.warningCount = (
            self.title, self.status, self.progress, self.progressText, self.canPause, self.canCancel, self.errorCount,
            self.warningCount
        )
        c.messages = copy.copy(self.messages)
        c.results = copy.copy(self.results)
        return c


class _CallbackRequestEvent(QEvent):
    _eventType = QEvent.registerEventType()

    def __init__(self, operation, callback, *callback_args, **callback_kwargs):
        super().__init__(self._eventType)
        self._operation = operation
        self._callback = callback
        self._callbackArgs = callback_args
        self._callbackKwArgs = callback_kwargs

    def __call__(self):
        if self._operation is not None and self._callback is not None and callable(self._callback):
            result = self._callback(*self._callbackArgs, **self._callbackKwArgs)
            self.accept()
            self._operation._reportCallbackProcessed(True, result)


class _GuiDispatcher(QObject):
    def __init__(self):
        QObject.__init__(self)
        self.moveToThread(qApp.thread())

    def customEvent(self, event):
        if isinstance(event, _CallbackRequestEvent):
            event()


_globalGuiDispatcher = None


def globalGuiDispatcher():
    global _globalGuiDispatcher
    if _globalGuiDispatcher is None:
        _globalGuiDispatcher = _GuiDispatcher()
    return _globalGuiDispatcher


class Operation(QObject):
    """Objects of Operation class are interface to communicate with code Running in operation context (another thread).
    Operation has set of parameters that define its state. Parameters are status (is operation Running, started, finished,
    etc), progress of operation (if available, can vary from 0.0 to 100.0), progress text describing action currently
    performed by operation.

    It is possible to send control messages (like pause, resume, cancel and any custom text strings) to operation.
    Operation code has two ways to receive these commands:
        - reimplement Operation.onCommandReceived which is called each time new command sent. Note that this method
          is called in context of thread that sends command.
        - periodically check for new commands with Operation.takeCommand method.
    In general case commands are processed asynchronically and there is no way to report sender that command was accepted
    or rejected.

    Code executed in operation context can send messages (information, warnings, errors) using Operation.addMessage method.

    To implement your own operation, you can use one of three methods:
        - create new class, inherited from Operation class, and reimplement Operation.doWork method. This method will be
          called immediately after starting operation. You can split your task into parts, where each execution of
          doWork will perform only one part of entire task. To make Operation.doWork to be called another time, you
          should set Operation.requestDoWork to True (this value resetted to False each time before calling doWork).
          Splitting operation into parts can be useful if operation executed in context of GUI thread as
          QCoreApplication.processEvents gets called after each iteration.
          Operation will be finished automatically after returning from doWork (if requestDoWork is False). Operation
          automatically determines final status by added messages: if there are error messages, final status will be
          OperationState.Failed, otherwise OperationState.Completed.
          You can call Operation._cancel to make operation finish with OperationState.Cancelled status.

        - use OperationContext class. In this case you can write something like this:

          with globalOperationContext().newOperation('my-cool-operation') as op:
              for p in range(101):
                  op.setProgress(p)

          Operation created in such a way will be executed in context of current thread. If code already executed in
          operation context, new sub-operation will be created and started. Operation will be automatically finished
          when control goes out of 'with' scope with final status Completed or Failed (if scope was left due to
          exception raised)

        - use WrapperOperation to execute any callable in operation context.
    """

    statusChanged = pyqtSignal(int)
    progressChanged = pyqtSignal(float)
    progressTextChanged = pyqtSignal(str)
    canPauseChanged = pyqtSignal(bool)
    canCancelChanged = pyqtSignal(bool)
    messageAdded = pyqtSignal(str, int)
    errorCountIncreased = pyqtSignal(int)
    warningCountIncreased = pyqtSignal(int)
    newResults = pyqtSignal(list)
    finished = pyqtSignal(int)
    started = pyqtSignal()

    # predefined commands for use with sendCommand
    PauseCommand = 'pause'
    ResumeCommand = 'resume'
    CancelCommand = 'cancel'

    RunModeNotStarted, RunModeThisThread, RunModeNewThread = range(3)

    DefaultErrorPolicy = 'default'
    IgnoreErrorPolicy = 'ignore'
    FailErrorPolicy = 'fail'
    AskErrorPolicy = 'ask'

    def __init__(self, title='', parent=None):
        QObject.__init__(self)
        self.lock = threading.RLock()

        self._state = OperationState()
        self._commandsQueue = queue.Queue()
        self._waitFinish = threading.Condition(self.lock)
        self._waitResults = threading.Condition(self.lock)
        self._manualScope = False  # if True, operation will not be automatically finished. Ignored if runMode ==
                                   # RunModeThisThread. This value should be set only by _InlineOperation class.
        self._daemon = None
        self._thread = None

        self._runMode = self.RunModeNotStarted
        self._requestDoWork = True
        self._state.title = title
        self._waitUserCallback = threading.Condition(self.lock)
        self._callbackAccepted = False
        self._callbackResult = None
        self._subOperationStack = []
        self._newResults = []
        self._resultsTimer = None

        self._errorPolicy = self.DefaultErrorPolicy

        self._parentOperation = parent

    def timerEvent(self, event):
        with self.lock:
            if event.timerId() == self._resultsTimer and self._newResults:
                self.newResults.emit(self._newResults)
                self._newResults = []

    @property
    def title(self):
        with self.lock:
            return self._state.title or utils.tr('<unnamed operation>')

    @property
    def state(self):
        with self.lock:
            # return self._state
            return copy.deepcopy(self._state)

    @property
    def runMode(self):
        with self.lock:
            return self._runMode

    @property
    def requestDoWork(self):
        with self.lock:
            return self._requestDoWork

    @requestDoWork.setter
    def requestDoWork(self, value):
        with self.lock:
            self._requestDoWork = value

    @property
    def errorPolicy(self):
        with self.lock:
            return self._errorPolicy

    @errorPolicy.setter
    def errorPolicy(self, new_policy):
        with self.lock:
            if self._errorPolicy != new_policy:
                self._errorPolicy = new_policy

    @property
    def parentOperation(self):
        with self.lock:
            return self._parentOperation

    @property
    def daemon(self):
        return self._daemon

    @property
    def opThread(self):
        return self._thread

    def sendCommand(self, command):
        """Send command to operation code. Operation can process commands in two ways:
        1. Reimplement onCommandReceived method which is called each time new command sent.
        This method should return True if command was processed.
        2. Use takeCommand method.
        """
        with self.lock:
            if not command:
                raise OperationError('invalid command')
            if not self.onCommandReceived(command):
                self._commandsQueue.put(command)

    def run(self, runMode=RunModeNewThread, daemon=False):
        """Start operation. Fails if operation already started.
        """
        with self.lock:
            if self._state.status != OperationState.NotStarted:
                raise OperationError('operation already started or waiting for start')
            if runMode not in (self.RunModeThisThread, self.RunModeNewThread):
                raise OperationError('invalid run mode')
            self._runMode = runMode
            self._daemon = daemon
            self.setStatus(OperationState.WaitingForStart)

        globalOperationContext()._enterOperation(self)
        globalOperationPool().addOperation(self)

    def sendPause(self):
        """Send pause command to operation. Note that this method does not check if pause
        command has any meaning at the moment.
        """
        self.sendCommand(self.PauseCommand)

    def sendResume(self):
        """Send resume command to operation. Note that this method does not check if resume
        command has any meaning at the moment.
        """
        self.sendCommand(self.ResumeCommand)

    def sendCancel(self):
        """Send cancel command to operation. Note that this method does not check if cancel
        command has any meaning at the moment.
        """
        self.sendCommand(self.CancelCommand)

    def togglePauseResume(self):
        """If operation state is OperationState.Paused, send resume command, if state is OperationState.Running,
        send pause command. Otherwise do nothing.
        """
        with self.lock:
            if self._state.status == OperationState.Running:
                self.sendPause()
            elif self._state.status == OperationState.Paused:
                self.sendResume()

    def join(self):
        """Block current thread until operation finished. Return operation final status.
        """
        with self._waitFinish:
            if threading.current_thread() is self.opThread:
                raise OperationError('deadlock detected: joining operation from same thread')
            if not self._state.isFinished:
                self._waitFinish.wait()
            return self._state.status

    def waitForResult(self):
        """Block current thread until operation adds new result to results list or
        operation finishes.
        """
        with self._waitResults:
            if threading.current_thread() is self.opThread:
                raise OperationError('deadlock detected: waiting for operation results from same thread')
            if not self._state.isFinished:
                self._waitResults.wait()

    def takeCommand(self, block=False, timeout=None):
        """Get oldest command from queue, removing it. Arguments :block: and :timeout: has
        same meaning as Queue.get arguments with same name. If there are no commands in queue, returns None.
        """
        try:
            return self._commandsQueue.get(block, timeout)
        except queue.Empty:
            return None

    def _start(self):
        with self.lock:
            self.setStatus(OperationState.Running)
            self.started.emit()
            self._resultsTimer = self.startTimer(300)

    def _finalize(self):
        with self.lock:
            if self._newResults:
                self.newResults.emit(self._newResults)
            self.killTimer(self._resultsTimer)
            self._resultsTimer = None

    def _finish(self):
        """Finish operation. If operation has error messages (state.errorCount > 0) final
        state will be OperationState.Failed, otherwise it will be set to OperationState.Completed.
        """
        with self.lock:
            if not self._state.isFinished:
                self._finalize()
                self.setProgress(100)
                self.setStatus(OperationState.Failed if self._state.errorCount > 0 else OperationState.Completed)

    def _cancel(self):
        """Cancel operation. Final state will be set to OperationState.Cancelled
        """
        with self.lock:
            if not self._state.isFinished:
                self._finalize()
                self.setStatus(OperationState.Cancelled)

    def doWork(self):
        """This method should be reimplemented to contain operation code.
        """
        raise NotImplementedError()

    def onCommandReceived(self, command):
        """Method called before received command will be placed into queue.
        If method returns true, command will be considered as processed and will not be placed into queue.
        This method is always executed in context of thread that sends command.
        """
        return False

    def _work(self):
        """Private method to execute operation code. Operation code contained in reimplemented
        Operation.doWork method will be executed at least once. Another sequential calls will be made
        if requestDoWork is True (this flag is reseted before calling doWork).
        Any exception raised in doWork is catched but will not be passed to outer methods: Operation.addMessage
        is called instead. Raised exception does not make operation to be finished.
        If operation executes in GUI thread, qApp.processEvents will be called after each iteration.
        """
        with self.lock:
            if self._state.isStarted:
                raise OperationError('operation already had been started')
            self._thread = threading.current_thread()
            self._start()
            self._requestDoWork = True
            while not self._state.isFinished:
                if self._requestDoWork:
                    self._requestDoWork = False
                    self.lock.release()
                    try:
                        self.doWork()
                    except Exception as exc:
                        self.addMessage(str(exc), logging.ERROR)
                        print('error inside operation: {0}'.format(exc))
                    except:
                        self.addMessage('undefined error while executing operation', logging.ERROR)
                    finally:
                        self.lock.acquire()

                    if threading.current_thread() is utils.guiThread:
                        qApp.processEvents()
                elif not self._manualScope or self.runMode == Operation.RunModeNewThread:
                    self._finish()
                else:
                    break

    def _setStateAttribute(self, attrib_name, value):
        with self.lock:
            if getattr(self._state, attrib_name) != value:
                setattr(self._state, attrib_name, value)
                attrib_signal = attrib_name + 'Changed'
                getattr(self, attrib_signal).emit(value)

    def setStatus(self, new_status):
        with self.lock:
            if self._state.status != new_status:
                if self._state.isFinished:
                    raise OperationError('operation tried to set status after finish')

                self._setStateAttribute('status', new_status)

                if self._state.isFinished:
                    self._waitFinish.notify_all()
                    self._waitResults.notify_all()

                    try:
                        self._callbackAccepted = False
                        self._waitUserCallback.notify_all()
                    except RuntimeError:
                        pass

                    globalOperationContext()._leaveOperation(self)
                    self.finished.emit(self._state.status)

    def setProgress(self, new_progress):
        if new_progress > 100:
            new_progress = 100
        if abs(new_progress - self._state.progress) >= 0.01:
            self._setStateAttribute('progress', new_progress)

    def setProgressText(self, new_progress_text):
        self._setStateAttribute('progressText', new_progress_text)

    def setCanPause(self, new_can_pause):
        self._setStateAttribute('canPause', new_can_pause)

    def setCanCancel(self, new_can_cancel):
        self._setStateAttribute('canCancel', new_can_cancel)

    def addResult(self, new_result_name, new_result_value):
        with self.lock:
            if self._state.isFinished:
                raise OperationError('operation already finished')

            self._state.results[new_result_name] = new_result_value
            self._newResults.append((new_result_name, new_result_value))
            self._waitResults.notify_all()

    def addMessage(self, message, level=logging.INFO):
        """Add message to operation message list. :level: should be from logging module level enumeration.
        Depending on message level, can automatically adjust error or warning count.
        """
        with self.lock:
            self._state.messages.append((message, level))
            if level >= logging.ERROR:
                self._state.errorCount += 1
            elif level == logging.WARNING:
                self._state.warningCount += 1

            self.messageAdded.emit(message, level)
            if level >= logging.ERROR:
                self.errorCountIncreased.emit(self._state.errorCount)
            elif level == logging.WARNING:
                self.warningCountIncreased.emit(self._state.warningCount)

    def executeSubOperation(self, subop, progress_weight=0.0, process_results=False,
                            result_name_converter=None, finish_on_fail=False):
        """Operation can execute sub-operation in its context. Operation that executes sub-operation
        is called parent of it. No new thread will be created for sub-operation.
        So this method will return control after sub-operation doWork cycle is over. If sub-operation
        uses manual scope, it can still be not finished.
        When sub-operation will be finished, progress of parent operation increases on progress_weight
        percents. During executing of sub-operation parent progress will change from its value at moment
        of calling this method to this value + progress_weight.
        Changing sub-operation progress text will cause parent operation progress text to be changed to
        sub-operation progress text. Parent progress text will be restored after child finish.
        Before executing sub-operation parent operation canPause and canCancel flags will be set to sub-operation
        corresponding values and restored after finishing.
        Messages logged by sub-operation will be logged to parent-operation also.

        If :process_results: is True, results generated by sub-operation will be added to parent operation too.
        If :finish_on_fail: is True, parent operation will be finished if sub-operation fails.

        This method should be used by operation code, not by code outside. Method should be called
        only from thread in which operation executes.
        """

        with self.lock:
            with subop.lock:
                if self._state.isFinished:
                    raise OperationError('cannot execute sub-operation in context of finished operation')
                if self._state.status != OperationState.Running:
                    raise OperationError('operation state should be Running to execute sub-operation')
                if subop.state.isStarted:
                    raise OperationError('invalid sub-operation: should be alive and not started')
                subop._parentOperation = self

                # normalize progress_weight value to be in range 0...100
                if progress_weight < 0.0:
                    progress_weight = 0.0
                elif progress_weight > 100.0:
                    progress_weight = 100.0

                self._subOperationStack.append((subop, copy.copy(self._state), progress_weight, process_results,
                                                result_name_converter, finish_on_fail))
                saved_state = self.state

                self.setCanPause(subop.state.canPause)
                self.setCanCancel(self._state.canCancel and subop.canCancel)
                self.setProgressText(subop.state.progressText or self._state.progressText)

                # if current progress value + progress_weight is greater 100, decrease
                # current progress
                if self._state.progress + progress_weight > 100.0:
                    self.setProgress(100.0 - progress_weight)

                # connect signals to make it possible to react on sub-op changes
                subop.progressChanged.connect(self._onSubopProgress, Qt.DirectConnection)
                subop.progressTextChanged.connect(self._onSubopProgressText, Qt.DirectConnection)
                subop.messageAdded.connect(self.addMessage, Qt.DirectConnection)
                subop.canPauseChanged.connect(self.setCanPause, Qt.DirectConnection)
                subop.canCancelChanged.connect(lambda canCancel: self.setCanCancel(saved_state.canCancel and canCancel),
                                               Qt.DirectConnection)
                subop.statusChanged.connect(self._onSubopStatus, Qt.DirectConnection)

                if process_results:
                    def add_sub_results(results):
                        for result_name, result_value in results:
                            self.addResult(result_name_converter(result_name) if result_name_converter is not None
                                                                              else result_name, result_value)

                    subop.newResults.connect(add_sub_results, Qt.DirectConnection)

                subop.finished.connect(self._onSubopFinish, Qt.DirectConnection)

                subop.run(self.RunModeThisThread)

    def _onSubopProgress(self, np):
        with self.lock:
            self.setProgress(self._subOperationStack[-1][1].progress + np * (self._subOperationStack[-1][2] / 100))

    def _onSubopProgressText(self, subop_progress_text):
        with self.lock:
            saved_state = self._subOperationStack[-1][1]
            self.setProgressText(subop_progress_text or saved_state.progressText)

    def _onSubopStatus(self, status):
        with self.lock:
            if status == OperationState.Running or status == OperationState.Paused:
                self.setStatus(status)

    def _onSubopFinish(self):
        with self.lock:
            sd = self._subOperationStack.pop()

            subop = sd[0]
            saved_state = sd[1]
            subop_progress_weight = sd[2]
            finish_on_fail = sd[5]

            # restore some state values
            self.setCanPause(saved_state.canPause)
            self.setCanCancel(saved_state.canPause)
            self.setProgress(saved_state.progress + subop_progress_weight)
            self.setProgressText(saved_state.progressText)

            if finish_on_fail and subop.state.status == OperationState.Failed:
                self._finish()  # final state will be set to OperationState.Failed as error messages
                                 # are directly written to operation

    def requestGuiCallback(self, callback, *callback_args, **callback_kwargs):
        """This method allows operation to request executing a piece of code in
        context of user (gui) thread. Method blocks current thread until
        given callback will be executed or rejected. Returns tuple (accepted, result).
        """

        # check if we are in gui thread already. In this case just invoke callback
        if threading.current_thread() is utils.guiThread:
            return True, callback(*callback_args, **callback_kwargs)
        else:
            with self.lock:
                self._callbackAccepted, self._callbackResult = False, None
                request_event = _CallbackRequestEvent(self, callback, *callback_args, **callback_kwargs)
                qApp.postEvent(globalGuiDispatcher(), request_event)
                self._waitUserCallback.wait()
                return self._callbackAccepted, self._callbackResult

    def _reportCallbackProcessed(self, accepted, result=None):
        with self.lock:
            self._callbackAccepted, self._callbackResult = accepted, result
            self._waitUserCallback.notify_all()

    def fatalError(self, error):
        """Get the action operation should take for when error occupied. Depending on
        errorPolicy value this method can demand to ignore error, cancel operation or
        ask user to make decision. When errorPolicy is AskErrorPolicy and gui callback
        with question messagebox was rejected, policy given in user settings will be used.
        Return True if operation should be cancelled, False otherwise.
        """

        globalSettings = settings.globalSettings()

        with self.lock:
            def ask_user(operation, error):
                ans = operation.requestGuiCallback(operation.askUserOnError, error=error)
                return ans[1] if ans[0] else globalSettings[appsettings.App_DefaultErrorPolicy] != self.IgnoreErrorPolicy

            if self.errorPolicy == self.AskErrorPolicy:
                return ask_user(self, error)
            elif self.errorPolicy == self.DefaultErrorPolicy:
                pol = globalSettings[appsettings.App_DefaultErrorPolicy]
                if pol == self.AskErrorPolicy:
                    return ask_user(self, error)
                else:
                    return pol != self.IgnoreErrorPolicy
            else:
                return self.errorPolicy != self.IgnoreErrorPolicy

    def askUserOnError(self, error):
        from hex.mainwin import globalMainWindow

        error_text = utils.tr('During executing operation') + '<br><b>' + self._state.title
        if self._state.progressText:
            error_text += ' (' + self._state.progressText + ') '
        error_text += ('</b><br>' + utils.tr('the following error occupied:') + '<br><br><b>' + str(error) +
                        utils.tr('</b><br><br>Do you want to try to cancel this operation?'))

        msgbox = QMessageBox(globalMainWindow)
        msgbox.setWindowTitle(utils.tr('{0} operation error').format(self.title))
        msgbox.setText(error_text)
        msgbox.setIcon(QMessageBox.Question)
        buttonCancelOperation = msgbox.addButton(utils.tr('Cancel operation'), QMessageBox.YesRole)
        buttonCancelOperation.setIcon(utils.getIcon('media-playback-stop'))
        buttonContinueOperation = msgbox.addButton(utils.tr('Continue operation'), QMessageBox.NoRole)
        msgbox.setDefaultButton(buttonCancelOperation)
        msgbox.setEscapeButton(buttonContinueOperation)
        msgbox.exec_()
        return msgbox.clickedButton() == buttonCancelOperation

    def processError(self, errmsg):
        with self.lock:
            if self.fatalError(errmsg):
                self.addMessage(errmsg, logging.ERROR)
                return True
            else:
                self.addMessage(errmsg, logging.WARNING)
                return False


class OperationContext(QObject):
    """This class provides access to operation object in context of which code is executed. It also helps writing
    operations without need to subclass Operation class. For example:

    with globalOperationContext().newOperation('special_operation') as context:
        with globalOperationContext().newOperation('sub_operation', 10) as context2:
            context.addMessage('hello, world!')

    If this code executed when there are no active operation, first OperationContext.newOperation call will create new
    InlineOperation and start it. Second block will create and execute sub-operation in context of operation created
    by first block. Both operations are automatically finished when control goes out of 'with' scope.
    """

    operationAdded = pyqtSignal(Operation)
    operationRemoved = pyqtSignal(Operation)

    def __init__(self):
        QObject.__init__(self)
        self.moveToThread(qApp.thread())
        self.lock = threading.RLock()
        self._operations = {}

    def operationsInThread(self, thread=None):
        if thread is None:
            thread = threading.current_thread()
        with self.lock:
            return self._operations.get(thread, [])

    @property
    def allOperations(self):
        with self.lock:
            return list(itertools.chain(*self._operations.values()))

    @property
    def currentOperation(self):
        with self.lock:
            thread = threading.current_thread()
            if thread.ident not in self._operations or not self._operations[thread.ident]:
                return None
            return self._operations[thread.ident][-1]

    @property
    def isInOperation(self):
        return self.currentOperation is not None

    def newOperation(self, title='', progress_weight=0, collect_results=False):
        inline_operation = _InlineOperation(title)
        with self.lock:
            if self.isInOperation:
                self.currentOperation.executeSubOperation(inline_operation, progress_weight, collect_results)
            else:
                inline_operation.run(Operation.RunModeThisThread)
            return inline_operation

    def _enterOperation(self, operation):
        # This method is called by Operation.run before OperationPool actually runs operation, so we do not know
        # which thread this operation belongs to. We connect to Operation.started signal to assign thread correctly.
        with self.lock:
            def started_slot_wrapper():
                self._onOperationStarted(operation)

            operation.started.connect(started_slot_wrapper, Qt.DirectConnection)
            if None not in self._operations:
                self._operations[None] = [operation]
            else:
                self._operations[None].append(operation)
            self.operationAdded.emit(operation)

    def _onOperationStarted(self, operation):
        with self.lock:
            if utils.first(op for op in self._operations[None] if op is operation):
                self._operations[None] = [op for op in self._operations[None] if op is not operation]
                if operation.opThread not in self._operations:
                    self._operations[operation.opThread.ident] = [operation]
                else:
                    self._operations[operation.opThread.ident].append(operation)

    def _leaveOperation(self, operation):
        with self.lock:
            thread_ident = operation.opThread.ident
            if thread_ident in self._operations:
                self._operations[thread_ident].pop()
                if not self._operations[thread_ident]:
                    del self._operations[thread_ident]
                self.operationRemoved.emit(operation)

    def requestGuiCallback(self, callback, **callback_args):
        if self.currentOperation is not None:
            return self.currentOperation.requestGuiCallback(callback, **callback_args)
        else:
            return True, callback(**callback_args)


_globalOperationContext = None


def globalOperationContext():
    global _globalOperationContext
    if _globalOperationContext is None:
        _globalOperationContext = OperationContext()
    return _globalOperationContext


class WrapperOperation(Operation):
    """Operation allows executing any callable as operation. Result is accessible in results dict under 'result' name.
    """

    ResultName = 'result'

    def __init__(self, functor=None, title='', parent=None):
        super().__init__(title, parent)
        self._functor = functor

    def doWork(self):
        try:
            if self._functor is not None:
                self.addResult(self.ResultName, self._functor())
        finally:
            self._finish()


class DelayOperation(Operation):
    """Operation that executes at least given given number of milliseconds and does nothing.
    """

    def __init__(self, delay, parent=None):
        super().__init__('delay for {0} seconds'.format(delay), parent)
        self._delay = delay

    def doWork(self):
        QTimer.singleShot(self._delay, self._finish)


class _InlineOperation(Operation):
    """This is helper class which allows executing of operations that are not implemented as a derived class.
    Supports context manager protocol.
    """

    def __init__(self, title, parent=None):
        super().__init__(title, parent)
        self._manualScope = True

    def doWork(self):
        pass

    def __enter__(self):
        return self

    def __exit__(self, t, v, tp):
        if t is not None:
            self.addMessage('exception: {0}'.format(t), logging.ERROR)
        self._finish()


class SequentialOperationGroup(Operation):
    class OperationData(object):
        def __init__(self):
            self.operation = None
            self.progressWeight = 0.0
            self.processResults = True
            self.resultNameConverter = None
            self.finishOnFail = True

    def __init__(self, title, parent=None, operations=None):
        Operation.__init__(self, title, parent)
        self._currentOperationIndex = 0
        self._operations = []
        if operations:
            for op in operations:
                self.appendOperation(op)

    def appendOperation(self, operation, progress_weight=0.0, process_results=True, result_name_converter=None,
                        finish_on_fail=True):
        with self.lock:
            op_data = self.OperationData()
            op_data.operation = operation
            op_data.progressWeight = progress_weight
            op_data.processResults = process_results
            op_data.resultNameConverter = result_name_converter
            op_data.finishOnFail = finish_on_fail
            self._operations.append(op_data)

    def doWork(self):
        if self._currentOperationIndex == 0:
            # split remaining progress weight between operations
            unweighted_ops_count = 0
            remaining_weight = 100.0
            for op_data in self._operations:
                if op_data.progressWeight <= 0:
                    unweighted_ops_count += 1
                else:
                    remaining_weight -= op_data.progressWeight

            if remaining_weight > 0.0 and unweighted_ops_count:
                weight_part = remaining_weight / unweighted_ops_count
                for op_data in self._operations:
                    if op_data.progressWeight <= 0:
                        op_data.progressWeight = weight_part

        if self._currentOperationIndex < len(self._operations):
            op_data = self._operations[self._currentOperationIndex]
            self.executeSubOperation(op_data.operation, op_data.progressWeight, op_data.processResults,
                                     op_data.resultNameConverter, op_data.finishOnFail)

            if not self._state.isFinished:
                self._currentOperationIndex += 1
                if self._currentOperationIndex < len(self._operations):
                    self.requestDoWork = True


class OperationPool(QObject):
    """Operation pool allows to limit number of parallel threads for operations."""

    def __init__(self):
        QObject.__init__(self)
        self.moveToThread(qApp.thread())
        self.lock = threading.RLock()
        self._waiting = []
        self._limit = settings.globalSettings()[appsettings.App_PoolOperationLimit]
        self._threadCount = 0  # number of threads in which operations are run

    def addOperation(self, new_operation):
        with self.lock:
            with new_operation.lock:
                assert new_operation.state.status == OperationState.WaitingForStart

                new_operation.finished.connect(self._onOperationFinished)

                if new_operation.runMode == Operation.RunModeNewThread and self._threadCount >= self._limit:
                    self._waiting.append(new_operation)
                else:
                    self._runOperation(new_operation)

    def _onOperationFinished(self):
        operation = self.sender()
        with self.lock:
            if operation.runMode == Operation.RunModeNewThread:
                self._threadCount -= 1
                if self._threadCount < self._limit and self._waiting:
                    self._runOperation(self._waiting.pop(0))

    def _runOperation(self, operation):
        with self.lock:
            if operation.runMode == Operation.RunModeThisThread:
                operation._work()
            elif operation.runMode == Operation.RunModeNewThread:
                threading.Thread(target=operation._work, daemon=operation.daemon).start()
                self._threadCount += 1


_globalOperationPool = None


def globalOperationPool():
    global _globalOperationPool
    if _globalOperationPool is None:
        _globalOperationPool = OperationPool()
    return _globalOperationPool


class OperationWidget(object):
    def __init__(self, deps):
        self._operation = None
        self._deps = deps
        self._stateChanged = True
        self._queryTimer = self.startTimer(200)

    @property
    def operation(self):
        return self._operation

    @operation.setter
    def operation(self, new_operation):
        old_operation = self._operation
        if self._operation is not None:
            for dep in self._deps:
                getattr(self._operation, dep + 'Changed').disconnect(self._onDepUpdated)

        self._operation = new_operation

        if self._operation is not None:
            for dep in self._deps:
                getattr(self._operation, dep + 'Changed').connect(self._onDepUpdated, Qt.DirectConnection)

        self._setOperation(old_operation, new_operation)

        self._updateState(self._operation.state if self._operation is not None else None)

    def _onDepUpdated(self):
        self._stateChanged = True

    def timerEvent(self, event):
        if event.timerId() == self._queryTimer and self._stateChanged:
            self._updateState(self._operation.state if self._operation is not None else None)

    def _updateState(self, state):
        raise NotImplementedError()

    def _setOperation(self, old_operation, new_operation):
        pass


class OperationProgressBar(QProgressBar, OperationWidget):
    def __init__(self, parent, operation=None):
        QProgressBar.__init__(self, parent)
        OperationWidget.__init__(self, ('progress', 'status'))
        self.setMinimum(0)
        self.setMaximum(10000)
        self.operation = operation

    def _updateState(self, state):
        self.setEnabled(state is not None)
        if state is not None:
            if not state.isFinished:
                if state.progress < 0:
                    # indeterminate
                    self.setMaximum(0)
                else:
                    self.setMaximum(10000)
                    self.setValue(int(state.progress * 100))
            else:
                self.setValue(self.maximum())


class OperationProgressTextLabel(QLabel, OperationWidget):
    def __init__(self, parent, operation=None):
        QLabel.__init__(self, parent)
        OperationWidget.__init__(self, ('progressText', ))
        self.setTextFormat(Qt.PlainText)
        self.operation = operation

    def _updateState(self, state):
        self.setEnabled(state is not None)
        if state is not None:
            self.setText(state.progressText.capitalize())


class OperationRunButton(OperationWidget):
    def __init__(self, operation=None, run_mode=Operation.RunModeNewThread, icon_mode=False):
        OperationWidget.__init__(self, ('status', 'canPause'))
        self.clicked.connect(self._onClicked)
        self.operation = operation
        self.runMode = run_mode
        self._iconMode = None
        self.iconMode = icon_mode

    def _updateState(self, state):
        self.setEnabled(state is not None)
        if state is not None:
            self._update(state)

    def _onClicked(self):
        if self._operation is None:
            return

        with self._operation.lock:
            state = self._operation.state
            if not state.isStarted:
                self._operation.run(self.runMode)
            elif state.status == OperationState.Running and state.canPause:
                self._operation.sendPause()
            elif state.status == OperationState.Paused and state.canPause:
                self._operation.sendResume()

    @property
    def iconMode(self):
        return self._iconMode

    @iconMode.setter
    def iconMode(self, icon_mode):
        if icon_mode != self._iconMode:
            self._iconMode = icon_mode
            self._update()

    def _update(self, state=None):
        if state is None:
            if self.operation is None:
                return
            state = self.operation.state

        if state.status == OperationState.NotStarted:
            if not self._iconMode:
                self.setText(utils.tr('Run'))
            else:
                self.setIcon(utils.getIcon('media-playback-start'))
            self.setEnabled(True)
        elif state.status == OperationState.Running:
            if not self._iconMode:
                self.setText(utils.tr('Pause'))
            else:
                self.setIcon(utils.getIcon('media-playback-pause'))
            self.setEnabled(state.canPause)
        elif state.status == OperationState.Paused:
            if not self._iconMode:
                self.setText(utils.tr('Resume'))
            else:
                self.setIcon(utils.getIcon('media-playback-start'))
            self.setEnabled(state.canPause)
        else:
            self.setEnabled(False)


class OperationRunPushButton(QPushButton, OperationRunButton):
    def __init__(self, parent, operation=None, run_mode=Operation.RunModeNewThread):
        QPushButton.__init__(self, parent)
        OperationRunButton.__init__(self, operation, run_mode)


class OperationRunToolButton(QToolButton, OperationRunButton):
    def __init__(self, parent, operation=None, run_mode=Operation.RunModeNewThread):
        QToolButton.__init__(self, parent)
        OperationRunButton.__init__(self, operation, run_mode)


class OperationCancelButton(OperationWidget):
    def __init__(self, operation=None, icon_mode=False):
        OperationWidget.__init__(self, ('status', 'canCancel'))
        self.clicked.connect(self._onClicked)
        self._iconMode = None
        self.iconMode = icon_mode
        self.operation = operation

    def _updateState(self, state):
        self.setEnabled(state is not None and state.isRunning and state.canCancel)

    def _onClicked(self):
        if self._operation is not None:
            with self._operation.lock:
                state = self._operation.state
                if state.isRunning and state.canCancel:
                    self._operation.sendCancel()

    @property
    def iconMode(self):
        return self._iconMode

    @iconMode.setter
    def iconMode(self, icon_mode):
        if icon_mode != self._iconMode:
            self._iconMode = icon_mode
            if not self._iconMode:
                self.setText(utils.tr('Abort'))
            else:
                self.setIcon(utils.getIcon('media-playback-stop'))


class OperationCancelPushButton(QPushButton, OperationCancelButton):
    def __init__(self, parent, operation=None):
        QPushButton.__init__(self, parent)
        OperationCancelButton.__init__(self, operation)


class OperationCancelToolButton(QToolButton, OperationCancelButton):
    def __init__(self, parent, operation=None):
        QToolButton.__init__(self, parent)
        OperationCancelButton.__init__(self, operation)


class OperationInfoWidget(QWidget, OperationWidget):
    def __init__(self, parent, operation=None):
        QWidget.__init__(self, parent)
        OperationWidget.__init__(self, tuple())
        self.setLayout(QHBoxLayout())
        self.layout().setContentsMargins(0, 0, 0, 0)

        self.label = OperationProgressTextLabel(self, operation)
        self.layout().addWidget(self.label)

        self.progressBar = OperationProgressBar(self, operation)
        self.layout().addWidget(self.progressBar)

        self.cancelButton = OperationCancelToolButton(self, operation)
        self.cancelButton.setAutoRaise(True)
        self.cancelButton.iconMode = True
        self.layout().addWidget(self.cancelButton)

        self.setMaximumSize(QSize(16777215, 15))

        self.operation = operation

    def _updateState(self, state):
        pass

    def _setOperation(self, old_operation, new_operation):
        self.label.operation = new_operation
        self.progressBar.operation = new_operation
        self.cancelButton.operation = new_operation
        OperationWidget._setOperation(self, old_operation, new_operation)


class OperationsInfoWidget(OperationInfoWidget):
    """Displays information about all operations running in application"""

    requestShowMore = pyqtSignal(Operation)
    ShowMoreManager, ShowMoreSignal = range(2)

    def __init__(self, parent, show_more_action=ShowMoreManager, context=None):
        OperationInfoWidget.__init__(self, parent)

        if context is None:
            context = globalOperationContext()

        self._context = context
        self._showMoreAction = show_more_action
        self.label.installEventFilter(self)
        self.progressBar.installEventFilter(self)

        context.operationAdded.connect(self._onOperationAdded)
        context.operationRemoved.connect(self._onOperationRemoved)

        operations = context.allOperations
        self._operationCount = len(operations)
        if operations:
            self.operation = operations[0]

        self._update()

    def _onOperationAdded(self, new_operation):
        if new_operation.parentOperation is None:
            self._operationCount += 1
            if self.operation is None:
                self.operation = new_operation
            self._update()

    def _onOperationRemoved(self, removed_operation):
        if removed_operation.parentOperation is None:
            if self._operationCount <= 0:
                return
            self._operationCount -= 1
            if removed_operation is self.operation:
                operations = self._context.allOperations
                self.operation = operations[0] if operations else None
            self._update()

    def _update(self):
        if self._operationCount > 1:
            self.progressBar.setFormat('%p% / {0}'.format(self._operationCount))
        else:
            self.progressBar.setFormat('%p%')

    def eventFilter(self, sender, event):
        if (sender is self.label or sender is self.progressBar) and event.type() == QEvent.MouseButtonPress:
            if event.modifiers() == Qt.NoModifier:
                if self._showMoreAction == self.ShowMoreManager:
                    if self._operationCount == 1:
                        OperationDialog(self, self.operation).exec_()
                    elif self._operationCount > 1:
                        OperationsDialog(self).exec_()
                elif self._showMoreAction == self.ShowMoreSignal:
                    self.requestShowMore.emit(self.operation)
                return True
        return False


class OperationMessagesList(QListView, OperationWidget):
    def __init__(self, parent, operation=None):
        QListView.__init__(self, parent)
        OperationWidget.__init__(self, tuple())
        self.operation = operation

    def _setOperation(self, old_operation, new_operation):
        self.setModel(OperationMessagesModel(new_operation) if new_operation is not None else None)

    def _updateState(self, state):
        pass


class OperationMessagesModel(QAbstractListModel):
    def __init__(self, operation):
        QAbstractListModel.__init__(self)
        self._operation = operation
        with operation.lock:
            self._messages = copy.copy(operation.state.messages)
            operation.messageAdded.connect(self._onMessageAdded, Qt.QueuedConnection)

    def _onMessageAdded(self, text, level):
        self.beginInsertRows(QModelIndex(), len(self._messages), len(self._messages))
        self._messages.append((text, level))
        self.endInsertRows()

    def rowCount(self, parent=QModelIndex()):
        return len(self._messages) if not parent.isValid() else 0

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid() or not (0 <= index.row() < len(self._messages)):
            return None
        if role == Qt.DisplayRole:
            return self._messages[index.row()][0]
        elif role == Qt.DecorationRole:
            level = self._messages[index.row()][1]
            if level >= logging.ERROR:
                return utils.getIcon('dialog-error')
            elif level >= logging.WARNING:
                return utils.getIcon('dialog-warning')


class OperationDialog(utils.Dialog, OperationWidget):
    def __init__(self, parent, operation=None):
        utils.Dialog.__init__(self, parent, name='operation_dialog')
        OperationWidget.__init__(self, tuple())
        self.resize(400, 250)

        self.setLayout(QVBoxLayout())

        self.progressTextLabel = OperationProgressTextLabel(self)
        self.layout().addWidget(self.progressTextLabel)

        self.progress = OperationProgressBar(self)
        self.layout().addWidget(self.progress)

        self.messageList = OperationMessagesList(self)
        self.layout().addWidget(self.messageList)

        self.buttonBox = QDialogButtonBox(self)
        self.runButton = OperationRunPushButton(self)
        self.buttonBox.addButton(self.runButton, QDialogButtonBox.ActionRole)
        self.cancelButton = OperationCancelPushButton(self)
        self.buttonBox.addButton(self.cancelButton, QDialogButtonBox.ActionRole)
        self.buttonBox.addButton(utils.tr('Close dialog'), QDialogButtonBox.RejectRole)
        self.buttonBox.rejected.connect(self.reject)
        self.layout().addWidget(self.buttonBox)

        self.operation = operation

    def _setOperation(self, old_operation, new_operation):
        for widget in (self.progressTextLabel, self.progress, self.messageList, self.runButton, self.cancelButton):
            setattr(widget, 'operation', new_operation)

    def _updateState(self, state):
        self.setWindowTitle(self.operation.title.capitalize())


class OperationsModel(QAbstractTableModel):
    """Displays operation data in table, with columns:
        1. title
        2. status
        3. progress
        4. progress text
    """

    OperationRole = Qt.UserRole

    def __init__(self, context=None):
        QAbstractTableModel.__init__(self)
        self._context = context or globalOperationContext()
        with self._context.lock:
            self._operations = copy.copy(self._context.allOperations)
            for op in self._operations:
                self._connectOperation(op)
            self._context.operationAdded.connect(self._onOperationAdded, Qt.QueuedConnection)
            self._context.operationRemoved.connect(self._onOperationRemoved, Qt.QueuedConnection)

    def rowCount(self, parent=QModelIndex()):
        return len(self._operations) if not parent.isValid() else 0

    def columnCount(self, parent=QModelIndex()):
        return 4 if not parent.isValid() else 0

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid() or not (0 <= index.row() < len(self._operations) or not (0 <= index.column() < 4)):
            return None
        if role == Qt.DisplayRole:
            operation = self._operations[index.row()]
            column = index.column()
            if column == 0:
                return operation.title
            elif column == 1:
                return operation.state.statusText
            elif column == 2:
                return round(operation.state.progress, 2)
            elif column == 3:
                return operation.state.progressText
        elif role == self.OperationRole:
            return self._operations[index.row()]

    _sectionNames = (utils.tr('Title'), utils.tr('Status'), utils.tr('Progress'), utils.tr('Progress text'))

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if orientation == Qt.Horizontal and role == Qt.DisplayRole:
            if 0 <= section < len(self._sectionNames):
                return self._sectionNames[section]

    def _onOperationAdded(self, new_operation):
        self.beginInsertRows(QModelIndex(), len(self._operations), len(self._operations))
        self._operations.append(new_operation)
        self._connectOperation(new_operation)
        self.endInsertRows()

    def _onOperationRemoved(self, removed_operation):
        operation_index = self._operationIndex(removed_operation)
        if operation_index.isValid():
            row = operation_index.row()
            self.beginRemoveRows(QModelIndex(), row, row)
            del self._operations[row]
            self.endRemoveRows()

    def _operationIndex(self, operation, column=0):
        for row_index in range(len(self._operations)):
            if self._operations[row_index] is operation:
                return self.index(row_index, column)
        return QModelIndex()

    def _operationIndexChanged(self, operation, column):
        index = self._operationIndex(operation, column)
        if index.isValid():
            self.dataChanged.emit(index, index)

    def _connectOperation(self, operation):
        conn_mode = Qt.QueuedConnection
        with operation.lock:
            operation.statusChanged.connect(lambda: self._operationIndexChanged(operation, 1), conn_mode)
            operation.progressChanged.connect(lambda: self._operationIndexChanged(operation, 2), conn_mode)
            operation.progressTextChanged.connect(lambda: self._operationIndexChanged(operation, 3), conn_mode)


class OperationsDialog(utils.Dialog):
    def __init__(self, parent, context=None):
        utils.Dialog.__init__(self, parent, name='operations_dialog')
        self._context = context or globalOperationContext()
        self.setWindowTitle(utils.tr('Operation manager'))

        self.operationsModel = OperationsModel(self._context)

        self.operationsList = QTreeView(self)
        self.operationsList.setModel(self.operationsModel)
        self.progressDelegate = OperationProgressDelegate()
        self.operationsList.setItemDelegateForColumn(2, self.progressDelegate)
        self.operationsList.doubleClicked.connect(self._onItemDoubleClicked)

        self.buttonBox = QDialogButtonBox(self)
        self.buttonBox.addButton(QDialogButtonBox.Close)
        self.buttonBox.rejected.connect(self.reject)

        self.setLayout(QVBoxLayout())
        self.layout().addWidget(self.operationsList)
        self.layout().addWidget(self.buttonBox)

    def _onItemDoubleClicked(self, index):
        operation = index.data(OperationsModel.OperationRole)
        if operation is not None:
            OperationDialog(self, operation).exec_()


class OperationProgressDelegate(QItemDelegate):
    def __init__(self):
        QItemDelegate.__init__(self)

    def paint(self, painter, option, index):
        opts = QStyleOptionProgressBarV2()

        progress = index.data()
        if progress < 0:
            opts.maximum = 0
        else:
            opts.maximum = 10000
            opts.progress = int(progress * 100)

        opts.rect = option.rect

        qApp.style().drawControl(QStyle.CE_ProgressBar, opts, painter, )


def onApplicationShutdown(mainWindow):
    """If there are Running non-daemon operations, we should ask user to terminate them
    """
    context = globalOperationContext()
    non_daemon = [op for op in context.allOperations if not op.daemon]
    if non_daemon:
        message_text = utils.tr('There are {0} operations running in background. You should cancel them '
                        'or wait for them to finish before exiting application. Currently the following '
                        'operations are running or waiting to be started:\n\n{1}').format(
            len(non_daemon), '\n'.join(op.state.title for op in non_daemon)
        )
        msgbox = QMessageBox(mainWindow)
        msgbox.setWindowTitle(utils.tr('Background operations are running'))
        msgbox.setText(message_text)
        msgbox.setIcon(QMessageBox.Question)
        cancelOpsButton = msgbox.addButton(utils.tr('Cancel all operations'), QMessageBox.YesRole)
        waitOpsButton = msgbox.addButton(utils.tr('Wait for operations to be finished'), QMessageBox.NoRole)
        msgbox.setDefaultButton(waitOpsButton)
        msgbox.setEscapeButton(cancelOpsButton)
        msgbox.exec_()

        if msgbox.clickedButton() is None:
            return False

        role = msgbox.buttonRole(msgbox.clickedButton())
        if role == QMessageBox.YesRole:
            # we will try to cancel all operations. This is not always possible...
            for op in non_daemon:
                op.sendCancel()

            # wait a second...
            qApp.processEvents()
            time.sleep(1)
            qApp.processEvents()

            if not [op for op in context.allOperations if not op.daemon]:
                return True
            else:
                QMessageBox.information(mainWindow, utils.tr('Failed to cancel operations'),
                                        utils.tr('Not all operations was cancelled. Application will stay alive.'),
                                        QMessageBox.Ok)
        return False
    else:
        return True
