#include "clipboard.h"
#include <climits>
#include <memory>
#include <QApplication>
#include <QClipboard>
#include <QMimeData>
#include <QStringList>
#include "document.h"
#include "chain.h"
#include "spans.h"


static const QString TextPlainMimeType("text/plain");
static const QString OctetStreamMimeType("application/octet-stream");
static const QString MicrohexDataMimeType("application/microhex-data");
static const QString MicrohexMarkMimeType("application/microhex-mark");

static QStringList _supportedMimeTypes = {TextPlainMimeType, OctetStreamMimeType,
                                          MicrohexDataMimeType, MicrohexMarkMimeType};

static const int BLOCK_SIZE = 1024 * 1024 * 32;
static const QString hex_digits("0123456789ABCDEF");
static const QString linebreak("\n");
static const QString whitespaces("\n \t\r");

QString dataToText(const std::shared_ptr<SpanChain> &chain, qulonglong position, qulonglong length) {
    qulonglong string_size = length * 3 + ((linebreak.length() - 1) * length / 16);
    if (string_size > INT_MAX) {
        throw std::bad_alloc();
    }

    QString result;
    result.reserve(int(string_size));

    qulonglong bytes_read = 0;
    qulonglong bytes_processed = 0;
    while (bytes_read < length) {
        qulonglong to_read = std::min(length - bytes_read, qulonglong(BLOCK_SIZE));
        QByteArray block = chain->read(position + bytes_read, to_read);
        bytes_read -= to_read;

        for (int j = 0; j < block.length(); ++j) {
            unsigned char byte = (unsigned char)(block.at(j));
            result.append(hex_digits.at(byte / 16));
            result.append(hex_digits.at(byte % 16));
            ++bytes_processed;
            if (bytes_processed % 16 == 0 && bytes_processed) {
                result.append(linebreak);
            } else {
                result.append(QChar(' '));
            }
        }
    }

    return result;
}

class DocumentMimeData : public QMimeData {
public:
    DocumentMimeData(const std::shared_ptr<const Document> &document, qulonglong position, qulonglong length)
        : QMimeData(), _document(document), _position(position), _length(length) {
        _chain = document->exportRange(position, length);
    }

    bool hasFormat(const QString &mimetype) const {
        return _supportedMimeTypes.contains(mimetype);
    }

    QStringList formats()const {
        return _supportedMimeTypes;
    }

    QVariant retrieveData(const QString &mimetype, QVariant::Type preferredType) const {
        Q_UNUSED(preferredType);
        if (mimetype == MicrohexDataMimeType) {
            void *pchain = _chain.get();
            return QByteArray((const char*)&pchain, sizeof(pchain) / sizeof(const char));
        } else if (mimetype == MicrohexMarkMimeType) {
            return QString("%1").arg(QCoreApplication::applicationPid());
        } else if (mimetype == OctetStreamMimeType) {
            return _chain->readAll();
        } else if (mimetype == TextPlainMimeType) {
            return dataToText(_chain, 0, _chain->getLength());
        } else {
            return QVariant();
        }
    }

private:
    std::shared_ptr<SpanChain> _chain;
    std::shared_ptr<const Document> _document;
    qulonglong _position, _length;
};

void Clipboard::setData(const std::shared_ptr<const Document> &document, qulonglong position, qulonglong length) {
    QApplication::clipboard()->setMimeData(new DocumentMimeData(document, position, length));
}

std::shared_ptr<SpanChain> Clipboard::getData() {
    const QMimeData *mimeData = QApplication::clipboard()->mimeData();
    if (mimeData->hasFormat(MicrohexMarkMimeType) && mimeData->hasFormat(MicrohexDataMimeType)) {
        QString datainfo = mimeData->data(MicrohexMarkMimeType);
        bool ok;
        qint64 sourcePid = datainfo.toLongLong(&ok);
        if (ok && sourcePid == QCoreApplication::applicationPid()) {
            // data copied from this process - just copy chain...
            const QByteArray pointer_data = mimeData->data(MicrohexDataMimeType);
            const SpanChain *chain = *(const SpanChain**)(pointer_data.constData());
            if (chain) {
                return SpanChain::fromChain(*chain);
            }
        }
    }

    // prefer compact application/octet-stream to other mime types
    if (mimeData->hasFormat(OctetStreamMimeType)) {
        QByteArray data = mimeData->data(OctetStreamMimeType);
        return SpanChain::fromSpans(SpanList() << std::make_shared<DataSpan>(data));
    }

    if (mimeData->hasText()) {
        // we assuming that text is hex values. In most cases this is false, but GUI should
        // resolve this ambiguity.
        QString clip_text = mimeData->text();
        if (!clip_text.isEmpty()) {
            // using QByteArray::fromHex is bad idea: it skips invalid characters.
            QByteArray data;
            QString text_buffer;
            for (int j = 0; j < clip_text.length(); ++j) {
                QChar ch = clip_text.at(j);
                if (whitespaces.indexOf(ch) == -1) {
                    text_buffer.append(ch);
                    if (text_buffer.length() == 2) {
                        bool ok = false;
                        data.append(text_buffer.toInt(&ok, 16));
                        text_buffer.clear();
                        if (!ok) {
                            data.clear();
                            break;
                        }
                    }
                }
            }
            if (!data.isEmpty()) {
                return SpanChain::fromSpans(SpanList() << std::make_shared<DataSpan>(data));
            }
        }
    }

    return nullptr;
}


bool Clipboard::hasMicrohexData() {
    const QMimeData *data = QApplication::clipboard()->mimeData();
    return data->hasFormat(MicrohexDataMimeType) && data->hasFormat(MicrohexMarkMimeType);
}


bool Clipboard::hasBinaryData() {
    if (!Clipboard::hasMicrohexData()) {
        const QMimeData *data = QApplication::clipboard()->mimeData();
        if (!data->hasFormat(OctetStreamMimeType)) {
            return false;
        }
    }
    return true;
}
