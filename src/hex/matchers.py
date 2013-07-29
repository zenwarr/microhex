import hex.operations as operations
import hex.utils as utils


class Match(object):
    def __init__(self, editor, position, length):
        self._editor = editor
        self._position = position
        self._length = length

    @property
    def editor(self):
        return self._editor

    @property
    def position(self):
        return self._position

    @property
    def length(self):
        return self._length


class Matcher(operations.Operation):
    def __init__(self, editor, title=None):
        if title is None:
            title = utils.tr('looking for matches')
        operations.Operation.__init__(self, title)
        self._editor = editor

    @property
    def allMatches(self):
        return self.state.results.values()

    def doWork(self):
        self.findMatches()

    def findMatches(self):
        raise NotImplementedError()


class BinaryMatcher(Matcher):
    def __init__(self, editor, find_what, title=None):
        Matcher.__init__(self, editor, title)
        self._resultCount = 0

        self.setCanPause(True)
        self.setCanCancel(True)

        if not isinstance(find_what, bytes):
            find_what = bytes(find_what)
        self._findWhat = find_what

        # build offset table
        self._offsetTable = [len(find_what)] * 256
        if find_what:
            for byte_index in range(len(find_what) - 1):
                byte = find_what[byte_index]
                self._offsetTable[byte] = len(find_what) - byte_index - 1

    def findMatches(self):
        self.setProgressText(utils.tr('searching... no matches yet'))

        cursor = self._editor.createReadCursor()
        with cursor.activate():
            if len(self._editor) < len(self._findWhat) or not self._findWhat:
                return

            counter = 0

            template = self._findWhat
            if len(template) == 1:
                # simply iterate over bytes with byteRange
                find_byte = template[0]
                byte_index = 0
                for byte in self._editor.byteRange(0, len(self._editor)):
                    if find_byte == byte:
                        self._addMatch(Match(self._editor, byte_index, 1))
                    byte_index += 1

                    if counter >= 1000:
                        self._updateState((byte_index / len(self._editor)) * 100)
                        counter = 0
                    else:
                        counter += 1
            else:
                template_end_position = len(template) - 1
                offset_table = self._offsetTable
                editor_length = len(self._editor)

                counter = 0
                while template_end_position < editor_length:
                    # find first byte that does not match template
                    for template_index in range(0, -len(template), -1):
                        if cursor[template_end_position + template_index] != template[template_index - 1]:
                            # shift template by offset
                            template_end_position += offset_table[cursor[template_end_position + template_index]]
                            break
                    else:
                        # sequence was found...
                        self._addMatch(Match(self._editor, template_end_position - len(template) + 1, len(template)))
                        template_end_position += 1

                    if counter >= 1000:
                        self._updateState((template_end_position / editor_length) * 100)
                        counter = 0
                    else:
                        counter += 1

            self.setProgressText(utils.tr('search completed: {0} results found').format(self._resultCount))

    def _addMatch(self, match):
        self._resultCount += 1
        self.addResult(str(self._resultCount), match)
        self.setProgressText(utils.tr('searching... {0} matches found').format(self._resultCount))

    def _updateState(self, progress):
        while True:
            command = self.takeCommand()
            if command == self.PauseCommand:
                self.setStatus(operations.OperationState.Paused)
                while True:
                    command = self.takeCommand(block=True)
                    if command == self.CancelCommand:
                        self.setProgressText(utils.tr('search cancelled - {0} results was found').format(self._resultCount))
                        self._cancel()
                        return
                    elif command == self.ResumeCommand:
                        self.setStatus(operations.OperationState.Running)
                        break
            elif command == self.CancelCommand:
                self._cancel()
                self.setProgressText(utils.tr('search cancelled - {0} results was found').format(self._resultCount))
                return
            else:
                break
        counter = 0
        self.setProgress(progress)
