#include "devices.h"
#include <cassert>
#include <cmath>
#include <ctime>
#include <QFileInfo>
#include <QBuffer>
#include "spans.h"
#include "document.h"

qulonglong DEFAULT_CACHE_SIZE = 1024 * 1024 * 8; // 8 MB
qulonglong DEFAULT_CACHE_BOUNDARY = 1024; // 1 KB
qulonglong MAXIMAL_WRITE_BLOCK = 1024 * 1024 * 64; // 64 MB


bool checkRangesIntersect(qulonglong start1, qulonglong length1, qulonglong start2, qulonglong length2) {
    if (start2 < start1) {
        qSwap(start1, start2);
        qSwap(length1, length2);
    }
    return start2 - start1 <= length1;
}

const char *postfixes[] = {"TB", "GB", "MB", "KB"};
const qulonglong q[] = {1024ull * 1024ull * 1024ull * 1024ull, 1024 * 1024 * 1024, 1024 * 1024, 1024};

QString formatSize(qulonglong size) {
    QString postfix;

    double number;
    for (int j = 0; j < 4; ++j) {
        if (size >= q[j]) {
            number = double(size) / q[j];
            postfix = postfixes[j];
            break;
        }
    }
    if (postfix.isEmpty()) {
        postfix = 'B';
        number = double(size);
    }

    QString result = QString::number(qRound64(number));
    if (result.endsWith(".0")) {
        result = result.mid(0, result.size() - 2);
    }
    return result + ' ' + postfix;
}

QString getTempFilename(const QString &base_filename, const QString &suffix) {
    QString generated = base_filename + "." + suffix;
    while (QFileInfo(generated).exists()) {
        std::srand(std::time(0));
        generated = base_filename + "." + suffix + "-" + QString::number(std::rand() % 1000);
    }
    return generated;
}

AbstractDevice::AbstractDevice(const QUrl &url, const LoadOptions &options)
    : _url(url), _cacheStart(0), _cacheSize(DEFAULT_CACHE_SIZE), _cacheBoundary(DEFAULT_CACHE_BOUNDARY),
      _loadOptions(options) {

}

AbstractDevice::~AbstractDevice() {

}

bool AbstractDevice::readOnly() const {
    return _loadOptions.readOnly;
}

QByteArray AbstractDevice::read(qulonglong position, qulonglong length) const {
    if (!length || position >= this->length()) {
        return QByteArray();
    } else if (position + length >= this->length()) {
        length = this->length() - position;
    }

    if (position >= _cacheStart && position < _cacheStart + _cache.length()) {
        // bytes are cached...
        qulonglong cache_offset = position - _cacheStart;
        if (length <= _cacheStart + _cache.length() - position) {
            // all requested range is in cache
            return _cache.mid(cache_offset, length);
        } else {
            // we should additionally read some data from device. Do not move cache.
            qulonglong cached_bytes_count = _cache.length() - cache_offset;
            return _cache.mid(cache_offset, cached_bytes_count) +
                    _read(_cacheStart + _cache.length(), length - cached_bytes_count);
        }
    } else if (_cacheSize > 0) {
        // cache is enabled, but we have cache miss. move it.
        _encache(position, true);
        // and try again
        return read(position, length);
    } else {
        // cache disabled - we can only read directly from device
        return _read(position, length);
    }
}

QByteArray AbstractDevice::readAll() const {
    return read(0, this->length());
}

void AbstractDevice::_encache(qulonglong from_position, bool center) const {
    assert(_cacheBoundary <= _cacheSize);

    qulonglong cache_start;
    if (center) {
        cache_start = from_position > _cacheSize / 2 ? from_position - _cacheSize / 2 : qulonglong(0);
        cache_start -= cache_start % _cacheBoundary;
        if (cache_start + _cacheSize <= from_position) {
            // byte at :from_position: is not in cache?
            cache_start = from_position - from_position % _cacheBoundary;
        }
    } else {
        cache_start = from_position - from_position % _cacheBoundary;
    }

    _cache = _read(cache_start, _cacheSize);
    _cacheStart = cache_start;
}

qulonglong AbstractDevice::write(qulonglong position, const QByteArray &data) {
    // writes data at :position:, overwriting existing data. Returns number of bytes actually written.
    qulonglong bytes_written = _write(position, data);
    if (checkRangesIntersect(position, data.length(), _cacheStart, _cache.length())) {
        // if we write into cached region, invalidate cache
        _cache = QByteArray();
    }
    return bytes_written;
}

AbstractSaver *AbstractDevice::createSaver(Document *document, AbstractDevice *read_device) {
    if (read_device == this && !document->checkCanQuickSave()) {
        throw IOError("it is impossible to save this document data to this device");
    }
    return new StandardSaver(read_device, this);
}

void AbstractDevice::setCacheSize(qulonglong size) {
    _cacheSize = size;
}

DeviceSpan *AbstractDevice::createSpan(qulonglong offset, qulonglong length) {
    if (offset >= this->length() || offset + length > this->length()) {
        throw OutOfBoundsError();
    }
    return new DeviceSpan(this, offset, length);
}

void AbstractDevice::_removeSpan(DeviceSpan *span)const {
    _spans.removeOne(span);
}

void AbstractDevice::_addSpan(DeviceSpan *span)const {
    _spans.append(span);
}

StandardSaver::StandardSaver(AbstractDevice *readDevice, AbstractDevice *writeDevice)
    : AbstractSaver(), _position(0), _readDevice(readDevice), _writeDevice(writeDevice) {

}

void StandardSaver::begin() {
    _writeDevice->resize(0);
}

void StandardSaver::putSpan(AbstractSpan *span) {
    qulonglong span_offset = 0;
    while (span_offset < span->length()) {
        qulonglong read_length = std::min(span->length() - span_offset, MAXIMAL_WRITE_BLOCK);
        QByteArray span_data = span->read(span_offset, read_length);
        if (_writeDevice->write(_position, span_data) != read_length) {
            throw IOError(QString("failed to write %1: not all data was written").arg(_writeDevice->url().toString()));
        }
        _position += span_data.length();
        span_offset += read_length;
    }
}

QtProxyDevice::QtProxyDevice(const QUrl &url, const LoadOptions &options)
    : AbstractDevice(url, options), _qdevice(0), _deviceClosed(true) {

}

qulonglong QtProxyDevice::length() const {
    return _qdevice->size();
}

void QtProxyDevice::_onDeviceAboutToClose() {
    _deviceClosed = true;
}

void QtProxyDevice::_ensureOpened() const {
    if (_deviceClosed) {
        if (!_qdevice->open(loadOptions().readOnly ? QIODevice::ReadOnly : QIODevice::ReadWrite)) {
            throw IOError(_qdevice->errorString());
        }
        _deviceClosed = false;
    }
}

void QtProxyDevice::_setQDevice(QIODevice *device) {
    assert(device && !_qdevice && !device->isSequential());
    if (device) {
        _qdevice = device;
        _deviceClosed = !_qdevice->isOpen();
        connect(device, SIGNAL(aboutToClose()), this, SLOT(_onDeviceAboutToClose()));
        device->setParent(this);
    }
}

QByteArray QtProxyDevice::_read(qulonglong position, qulonglong length) const {
    _ensureOpened();
    if (!_qdevice->seek(position)) {
        throw IOError("failed to seek to position");
    }
    return _qdevice->read(length);
}

qulonglong QtProxyDevice::_write(qulonglong position, const QByteArray &data) {
    _ensureOpened();
    if (!_qdevice->seek(position)) {
        throw IOError("failed to seek to position");
    }
    return _qdevice->write(data);
}

FileDevice::FileDevice(const QString &filename, const FileLoadOptions &options)
    : QtProxyDevice(QUrl::fromLocalFile(filename), options), _fileLoadOptions(options) {
    QFileInfo file_info = QFileInfo(filename);
    if (!fileLoadOptions().forceNew && !file_info.exists()) {
        return;
    }
    _setQDevice(new QFile(filename));
    if (fileLoadOptions().memoryLoad) {
        setCacheSize(_qdevice->size());
        _encache(0, false);
    }
}

bool FileDevice::fixedSize()const {
    return fileLoadOptions().freezeSize;
}

void FileDevice::resize(qulonglong new_size) {
    _ensureOpened();
    if (!dynamic_cast<QFile*>(qdevice())->resize(new_size)) {
        throw IOError(QString("failed to resize file %1 to size %2").arg(url().toLocalFile(),
                                                                         formatSize(new_size)));
    }
}

class FileSaver : public StandardSaver {
public:
    FileSaver(AbstractDevice *readDevice, FileDevice *writeDevice)
        : StandardSaver(readDevice, nullptr), _targetDevice(writeDevice), _tempDevice() {
        FileLoadOptions temp_file_options;
        temp_file_options.forceNew = true;
        _tempDevice = new FileDevice(getTempFilename(writeDevice->url().toLocalFile(), "mhs"), temp_file_options);
        _writeDevice = _tempDevice;
    }

    void complete() {
        QFile *target_file = dynamic_cast<QFile*>(_targetDevice->qdevice());
        QFile *temp_file = dynamic_cast<QFile*>(_tempDevice->qdevice());

        // remove target file
        target_file->remove();

        // and move temporary file at this place
        temp_file->rename(_targetDevice->url().toLocalFile());
    }

private:
    AbstractDevice *_readDevice;
    FileDevice *_targetDevice, *_tempDevice;
};


class QuickFileSaver : public StandardSaver {
public:
    QuickFileSaver(Document *document, AbstractDevice *readDevice, FileDevice *writeDevice)
        : StandardSaver(readDevice, writeDevice), _document(document) {

    }

    void begin() {
        // no need to clear device before saving, but resize file to document size
        _writeDevice->resize(_document->length());
    }

    void putSpan(AbstractSpan *span) {
        DeviceSpan *deviceSpan = dynamic_cast<DeviceSpan*>(span);
        if (deviceSpan && deviceSpan->device() == _writeDevice) {
            // skip all spans from this device. We assume that no spans are moved.
            _position += span->length();
        } else {
            StandardSaver::putSpan(span);
        }
    }

private:
    Document *_document;
};

AbstractSaver *FileDevice::createSaver(Document *document, AbstractDevice *read_device) {
    AbstractSaver *saver;
    if (document->checkCanQuickSave()) {
        saver = new QuickFileSaver(document, read_device, this);
    } else {
        saver = new FileSaver(read_device, this);
    }
    saver->setParent(this);
    return saver;
}

BufferDevice::BufferDevice(QByteArray *array, const LoadOptions &options)
    : QtProxyDevice(QUrl("data://"), options) {
    _setQDevice(new QBuffer(array));
}

bool BufferDevice::fixedSize() const {
    return false;
}

void BufferDevice::resize(qulonglong new_size) {
    if (new_size > qulonglong(INT_MAX)) {
        throw OutOfBoundsError();
    }
    dynamic_cast<QBuffer*>(qdevice())->buffer().resize(static_cast<int>(new_size));
}

