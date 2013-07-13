from PyQt4.QtCore import QObject, pyqtSignal


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


class Matcher(QObject):
    newMatch = pyqtSignal(Match)
    cleared = pyqtSignal()
    completed = pyqtSignal()

    def __init__(self, editor):
        QObject.__init__(self)
        self._editor = editor
        self._matches = []
        self.matchLimit = -1

    @property
    def allMatches(self):
        return self._matches

    def addMatch(self, match):
        self._matches.append(match)
        self.newMatch.emit(match)

    def findMatches(self):
        raise NotImplementedError()


class BinaryMatcher(Matcher):
    def __init__(self, editor, find_what):
        Matcher.__init__(self, editor)
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
        self._matches = []
        self.cleared.emit()

        cursor = self._editor.createReadCursor()
        with cursor.activate():
            if len(self._editor) < len(self._findWhat) or not self._findWhat:
                self.completed.emit()
                return

            template = self._findWhat
            template_end_position = len(template) - 1
            offset_table = self._offsetTable
            editor_length = len(self._editor)

            while template_end_position < editor_length:
                # find first byte that does not match template
                for template_index in range(0, -len(template), -1):
                    if cursor[template_end_position + template_index] != template[template_index - 1]:
                        # shift template by offset
                        template_end_position += offset_table[cursor[template_end_position + template_index]]
                        break
                else:
                    # sequence was found...
                    self.addMatch(Match(self._editor, template_end_position - len(template) + 1, len(template)))
                    if len(self._matches) >= self.matchLimit:
                        self.completed.emit()
                        return
                    template_end_position += 1

            self.completed.emit()
