import hex.operations as operations
import hex.utils as utils
import hex.documents as documents


class Match(object):
    def __init__(self, document=None, position=-1, length=-1):
        self._document = document
        self._position = position
        self._length = length

    @property
    def document(self):
        return self._document

    @property
    def position(self):
        return self._position

    @property
    def length(self):
        return self._length

    def __len__(self):
        return self._length

    @property
    def valid(self):
        return not (self._document is None or self._position < 0 or self._length < 0)


class AbstractMatcher(operations.Operation):
    def __init__(self, document, title=None):
        if title is None:
            title = utils.tr('looking for matches')
        operations.Operation.__init__(self, title)
        self._document = document
        self._resultCount = 0

        self.setCanPause(True)
        self.setCanCancel(True)

    @property
    def document(self):
        return self._document

    def _updateState(self, position):
        while True:
            command = self.takeCommand()
            if command == self.PauseCommand:
                self.setStatus(operations.OperationState.Paused)
                while True:
                    command = self.takeCommand(block=True)
                    if command == self.CancelCommand:
                        self.setProgressText(utils.tr('search cancelled - {0} results was found').format(self._resultCount))
                        self._cancel()
                        return True
                    elif command == self.ResumeCommand:
                        self.setStatus(operations.OperationState.Running)
                        break
            elif command == self.CancelCommand:
                self._cancel()
                self.setProgressText(utils.tr('search cancelled - {0} results was found').format(self._resultCount))
                return True
            else:
                break
        self.setProgress((position / self.document.length) * 100)
        return False

    @property
    def allMatches(self):
        return self.state.results.values()

    def addResult(self, name, value):
        self._resultCount += 1
        operations.Operation.addResult(self, name, value)


class BinaryMatcher(AbstractMatcher):
    def __init__(self, document, find_what, intersect=False, title=None):
        AbstractMatcher.__init__(self, document, title)
        self._findWhat = find_what
        self._intersect = intersect
        self._finder = documents.BinaryFinder(document, find_what)

    def doWork(self):
        self.setProgressText(utils.tr('searching...'))
        current_position = 0
        step = 1024 * 1024
        while current_position < self.document.length:
            match_position, found = self._finder.findNext(current_position, self.document.length - current_position)
            if found:
                self.addResult(str(self._resultCount), Match(self.document, match_position, len(self._findWhat)))
                if self._intersect:
                    current_position = match_position + 1
                else:
                    current_position = match_position + len(self._findWhat)
            else:
                current_position += step

            self._updateState(current_position)

        self.setProgressText(utils.tr('search completed: {0} matches found').format(len(self.allMatches)))

    def _doFind(self, from_position, limit, is_reversed):
        if limit is None:
            if is_reversed:
                limit = from_position
            else:
                limit = max(0, self._document.length - from_position)

        if limit == 0:
            return Match()

        if not is_reversed:
            match_position, found = self._finder.findNext(from_position, limit)
        else:
            match_position, found = self._finder.findPrevious(from_position, limit)

        if found:
            return Match(self._document, match_position, len(self._findWhat))
        else:
            return Match()

    def findNext(self, from_position, limit=None):
        return self._doFind(from_position, limit, False)

    def findPrevious(self, from_position, limit=None):
        return self._doFind(from_position, limit, True)
