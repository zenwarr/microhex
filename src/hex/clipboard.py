import hex.formatters as formatters
from hex.editor import DataSpan
from PyQt4.QtCore import QMimeData
from PyQt4.QtGui import QApplication
from PyQt4.QtNetwork import QTcpServer, QHostAddress


class Clipboard(object):
    def __init__(self):
        pass

    def copy(self, editor, position, length):
        """Data is exported in two formats: highly compatible with another applications text/plain and
        custom format for quick internal exchange.
        In text/plain bytes are always represented as hex values separated by spaces. Text is not splitted into
        lines.
        """

        data_to_copy = editor.read(position, length)
        if not data_to_copy:
            return

        mime_data = QMimeData()

        formatter = formatters.IntegerFormatter(base=16, padding=2)
        text = ' '.join(formatter.format(byte) for byte in data_to_copy)
        mime_data.setText(text)

        QApplication.clipboard().setMimeData(mime_data)

    def spanFromData(self, editor):
        if QApplication.clipboard().mimeData().hasText():
            try:
                splitted_text = QApplication.clipboard().mimeData().text().split()

                formatter = formatters.IntegerFormatter(base=16)
                data = bytes([formatter.parse(c) for c in splitted_text if c])
                return DataSpan(editor, data)
            except ValueError:
                return None
        return None


class ClipboardServer(QTcpServer):
    def __init__(self):
        QTcpServer.__init__(self)
        self.newConnection.connect(self._onNewConnection)

    def _onNewConnection(self):
        connection = self.nextPendingConnection()
        if connection.localAddress() != QHostAddress.LocalHost:
            connection.close()
