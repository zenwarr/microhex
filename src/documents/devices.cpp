#include "devices.h"
#include <cassert>
#include <cmath>
#include <ctime>
#include <algorithm>
#include <functional>
#include <iterator>
#include <QFileInfo>
#include <QBuffer>
#include <QMutex>
#include <QDebug>
#include "spans.h"
#include "document.h"


qulonglong DEFAULT_CACHE_SIZE = 1024 * 1024 * 8; // 8 MB
qulonglong DEFAULT_CACHE_BOUNDARY = 1024 * 1024; // 1 MB
qulonglong MAXIMAL_WRITE_BLOCK = 1024 * 1024 * 64; // 64 MB


static QList<AbstractDevice*> _allDevices;
static QMutex _allDevicesMutex;


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

    double number = size;
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

AbstractDevice::AbstractDevice(const QUrl &url, LoadOptions *options)
    : _loadOptions(options), _url(url), _cacheStart(0), _cacheSize(DEFAULT_CACHE_SIZE),
      _cacheBoundary(DEFAULT_CACHE_BOUNDARY), _lock(std::make_shared<ReadWriteLock>()) {
    // we cannot process LoadOptions.memoryLoad flag here, because we should encache device contents not on first access,
    // but when device is created. We cannot do this in constructor, as inherited class virtual methods are not available
    // at this moment. LoadOptions.memoryLoad is processed in deviceFromUrl factory function.
}

AbstractDevice::~AbstractDevice() {
    QMutexLocker locker(&_allDevicesMutex);
    _allDevices.removeOne(this);
}

bool AbstractDevice::isReadOnly() const {
    return _loadOptions->readOnly;
}

qulonglong AbstractDevice::getLength()const {
    ReadLocker locker(_lock);
    return _loadOptions->rangeLoad ? _loadOptions->rangeLength : _totalLength();
}

QByteArray AbstractDevice::read(qulonglong position, qulonglong length) const {
    ReadLocker locker(_lock);

    if (position + length < position) {
        throw std::overflow_error("integer overflow");
    } else if (!length || position >= this->getLength()) {
        return QByteArray();
    } else if (this->getLength() - position < length) {
        length = this->getLength() - position;
    }

    if (position >= _cacheStart && position < _cacheStart + _cache.length()) {
        // bytes are cached...
        qulonglong cache_offset = position - _cacheStart;
        if (length <= _cacheStart + _cache.length() - position) {
            // all requested range is in cache
            return _cache.mid(cache_offset, length);
        } else {
            // we should additionally read some data from device. Do not move cache - it can cause problems
            qulonglong cached_bytes_count = _cache.length() - cache_offset;
            return _cache.mid(cache_offset, cached_bytes_count) +
                    _read(_cacheStart + _loadOptions->rangeStart + _cache.length(), length - cached_bytes_count);
        }
    } else if (_cacheSize > 0) {
        // cache is enabled, but we have cache miss. move it.
        _encache(position, true);
        // and try again
        return read(position, length);
    } else {
        // cache disabled - we can only read directly from device
        return _read(position + _loadOptions->rangeStart, length);
    }
}

QByteArray AbstractDevice::readAll() const {
    ReadLocker locker(_lock);
    return read(0, this->getLength());
}

void AbstractDevice::_encache(qulonglong from_position, bool center) const {
    ReadLocker locker(_lock);
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

    _cache = _read(cache_start + _loadOptions->rangeStart, _cacheSize);
    _cacheStart = cache_start;
}

qulonglong AbstractDevice::write(qulonglong position, const QByteArray &data) {
    WriteLocker locker(_lock);

    if (position + data.size() < position) {
        throw std::overflow_error("integer overflow");
    }

    // writes data at :position:, overwriting existing data. Returns number of bytes actually written.
    if (isReadOnly()) {
        throw ReadOnlyError();
    } else if (isFixedSize() && (position >= getLength() || getLength() - data.length() < position)) {
        throw FrozenSizeError();
    }

    qulonglong bytes_written = _write(position + _loadOptions->rangeStart, data);
    if (checkRangesIntersect(position, data.length(), _cacheStart, _cache.length())) {
        // if we write into cached region, invalidate cache
        _cache = QByteArray();
    }
    return bytes_written;
}

void AbstractDevice::resize(qulonglong new_size) {
    WriteLocker locker(_lock);

    if (new_size != getLength()) {
        if (_loadOptions->freezeSize || _loadOptions->rangeLoad) {
            throw FrozenSizeError();
        }
        _resize(new_size);
    }
}

std::shared_ptr<AbstractSaver> AbstractDevice::createSaver(const std::shared_ptr<Document> &document,
                                                           const std::shared_ptr<AbstractDevice> &read_device) {
    WriteLocker locker(_lock);
    if (read_device.get() == this && !document->checkCanQuickSave()) {
        throw DeviceError("it is impossible to save this document data to this device");
    }
    return std::make_shared<StandardSaver>(document, read_device, shared_from_this());
}

void AbstractDevice::setCacheSize(qulonglong size) {
    _cacheSize = size;
}

QList<std::shared_ptr<PrimitiveDeviceSpan> > AbstractDevice::getSpans() const {
    QList<std::shared_ptr<PrimitiveDeviceSpan>> result;
    for (auto span : _spans) {
        result.append(std::dynamic_pointer_cast<PrimitiveDeviceSpan>(span->shared_from_this()));
    }
    return result;
}

std::shared_ptr<PrimitiveDeviceSpan> AbstractDevice::createSpan(qulonglong position, qulonglong length) {
    ReadLocker locker(_lock);
    if (position >= getLength() || getLength() - length < position) {
        throw OutOfBoundsError();
    }
    auto new_span = std::shared_ptr<PrimitiveDeviceSpan>(new PrimitiveDeviceSpan(shared_from_this(),
                                                                                 position, length));
    _spans.append(new_span.get());
    return new_span;
}

void AbstractDevice::_removeSpan(PrimitiveDeviceSpan *span) {
    ReadLocker locker(_lock);
    _spans.removeOne(span);
}

StandardSaver::StandardSaver(const std::shared_ptr<Document> &document,
                             const std::shared_ptr<AbstractDevice> &readDevice,
                             const std::shared_ptr<AbstractDevice> &writeDevice)
    : AbstractSaver(), _position(0), _readDevice(readDevice), _writeDevice(writeDevice), _document(document) {

}

void StandardSaver::begin() {
    _writeDevice->resize(_document->getLength());
}

void StandardSaver::putSpan(const std::shared_ptr<const AbstractSpan> &span) {
    qulonglong span_offset = 0;
    while (span_offset < span->getLength()) {
        qulonglong read_length = std::min(span->getLength() - span_offset, MAXIMAL_WRITE_BLOCK);
        QByteArray span_data = span->read(span_offset, read_length);
        if (_writeDevice->write(_position, span_data) != read_length) {
            throw DeviceError(QString("failed to write %1: not all data was written").arg(_writeDevice->getUrl().toString()));
        }
        _position += span_data.length();
        span_offset += read_length;
    }
}

QtProxyDevice::QtProxyDevice(const QUrl &url, LoadOptions *options)
    : AbstractDevice(url, options), _qdevice(0), _deviceClosed(true) {

}

qulonglong QtProxyDevice::_totalLength() const {
    return _qdevice->size();
}

void QtProxyDevice::_onDeviceAboutToClose() {
    _deviceClosed = true;
}

void QtProxyDevice::_ensureOpened() const {
    if (_deviceClosed) {
        bool read_only_changed = false;
        QIODevice::OpenMode open_mode = _loadOptions->readOnly ? QIODevice::ReadOnly : QIODevice::ReadWrite;
        if (!_qdevice->open(open_mode)) {
            // are we trying to open read only file with read-write access?
            if (!_loadOptions->readOnly && _qdevice->open(QIODevice::ReadOnly)) {
                _loadOptions->readOnly = true;
                read_only_changed = true;
            } else {
                throw DeviceError(_qdevice->errorString());
            }
        }

        _deviceClosed = false;
        if (read_only_changed) {
            emit readOnlyChanged(true);
        }
    }
}

void QtProxyDevice::_setQDevice(const std::shared_ptr<QIODevice> &device) {
    assert(device.get() && !_qdevice.get() && !device->isSequential());
    _qdevice = device;
    _deviceClosed = !_qdevice->isOpen();
    connect(device.get(), SIGNAL(aboutToClose()), this, SLOT(_onDeviceAboutToClose()));
}

QByteArray QtProxyDevice::_read(qulonglong position, qulonglong length) const {
    _ensureOpened();
    if (!_qdevice->seek(position)) {
        throw DeviceError("failed to seek to position");
    }
    return _qdevice->read(length);
}

qulonglong QtProxyDevice::_write(qulonglong position, const QByteArray &data) {
    _ensureOpened();
    if (!_qdevice->seek(position)) {
        throw DeviceError("failed to seek to position");
    }
    return _qdevice->write(data);
}

FileDevice::FileDevice(const QString &filename, FileLoadOptions *options)
                      : QtProxyDevice(QUrl::fromLocalFile(filename), options) {
    QFileInfo file_info = QFileInfo(filename);
    if (!getFileLoadOptions().forceNew && !file_info.exists()) {
        throw DeviceError(QString("file %1 does not exist").arg(file_info.fileName()));
    }
    _setQDevice(std::make_shared<QFile>(filename));
}

bool FileDevice::isFixedSize()const {
    return getFileLoadOptions().freezeSize;
}

void FileDevice::_resize(qulonglong new_size) {
    _ensureOpened();
    if (!std::dynamic_pointer_cast<QFile>(getQDevice())->resize(new_size)) {
        throw DeviceError(QString("failed to resize file %1 to size %2").arg(getUrl().toLocalFile(),
                                                                         formatSize(new_size)));
    }
}

class FileSaver : public StandardSaver {
public:
    FileSaver(const std::shared_ptr<Document> &document, const std::shared_ptr<AbstractDevice> &readDevice,
              const std::shared_ptr<FileDevice> &writeDevice)
              : StandardSaver(document, readDevice, nullptr), _targetDevice(writeDevice), _tempDevice() {
        FileLoadOptions temp_file_options;
        temp_file_options.forceNew = true;
        _tempDevice = deviceFromFile(getTempFilename(writeDevice->getUrl().toLocalFile(), "mhs"), temp_file_options);
        _writeDevice = _tempDevice;
    }

    void complete() {
        auto target_file = std::dynamic_pointer_cast<QFile>(_targetDevice->getQDevice());
        auto temp_file = std::dynamic_pointer_cast<QFile>(_tempDevice->getQDevice());

        // remove target file
        target_file->remove();

        // and move temporary file at this place
        temp_file->rename(_targetDevice->getUrl().toLocalFile());
    }

private:
    std::shared_ptr<FileDevice> _targetDevice, _tempDevice;
};


class QuickFileSaver : public StandardSaver {
public:
    QuickFileSaver(const std::shared_ptr<Document> &document, const std::shared_ptr<AbstractDevice> &readDevice,
                   const std::shared_ptr<FileDevice> &writeDevice)
        : StandardSaver(document, readDevice, writeDevice) {

    }

    void begin() {
        // no need to clear device before saving, but resize file to document size
        _writeDevice->resize(_document->getLength());
    }

    void putSpan(const std::shared_ptr<AbstractSpan> &span) {
        auto device_span = std::dynamic_pointer_cast<const PrimitiveDeviceSpan>(span);
        if (device_span) {
            _position += span->getLength();
        } else {
            StandardSaver::putSpan(span);
        }
    }
};

std::shared_ptr<AbstractSaver> FileDevice::createSaver(const std::shared_ptr<Document> &document,
                                                       const std::shared_ptr<AbstractDevice> &read_device) {
    if (read_device.get() == this && document->checkCanQuickSave()) {
        return std::make_shared<QuickFileSaver>(document, read_device,
                                                std::dynamic_pointer_cast<FileDevice>(shared_from_this()));
    } else {
        return std::make_shared<FileSaver>(document, read_device,
                                           std::dynamic_pointer_cast<FileDevice>(shared_from_this()));
    }
}

const FileLoadOptions &FileDevice::getFileLoadOptions() const {
    return dynamic_cast<const FileLoadOptions&>(getLoadOptions());
}

BufferDevice::BufferDevice(BufferLoadOptions *options) : QtProxyDevice(QUrl("microdata://"), options) {
    _setQDevice(std::make_shared<QBuffer>(&options->data));
}

bool BufferDevice::isFixedSize() const {
    return false;
}

void BufferDevice::_resize(qulonglong new_size) {
    if (new_size > qulonglong(INT_MAX)) {
        throw OutOfBoundsError();
    }
    std::dynamic_pointer_cast<QBuffer>(getQDevice())->buffer().resize(static_cast<int>(new_size));
}

const BufferLoadOptions &BufferDevice::getBufferLoadOptions() const {
    return dynamic_cast<const BufferLoadOptions&>(getLoadOptions());
}

void LoadOptions::copyBaseFrom(const LoadOptions &options) {
    readOnly = options.readOnly;
    rangeLoad = options.rangeLoad;
    memoryLoad = options.memoryLoad;
    rangeStart = options.rangeStart;
    rangeLength = options.rangeLength;
}

static bool canLoadDevice(const QUrl &url, const LoadOptions &options) {
    // check if device requested to be opened does not conflict with already open device.
    // Two device are considered conflicting if at least one of them is not read-only and both has access to same data.
    for (auto device : _allDevices) {
        if (device->isSharedResource() && device->getUrl() == url) {
            // check if ranges are intersect
            const LoadOptions &e_options = device->getLoadOptions();
            if (!e_options.rangeLoad || !options.rangeLoad) {
                return false;
            } else if (checkRangesIntersect(e_options.rangeStart, e_options.rangeLength,
                                            options.rangeStart, options.rangeLength) &&
                       (!e_options.readOnly || !options.readOnly)) {
                return false;
            }
        }
    }
    return true;
}

std::shared_ptr<AbstractDevice> deviceFromUrl(const QUrl &url, const LoadOptions &options) {
    std::shared_ptr<AbstractDevice> device;

    if (!canLoadDevice(url, options)) {
        throw DeviceError(QObject::tr("cannot load device with given options: conflict with already loaded device"));
    }

    if (url.isLocalFile()) {
        QString local_file_path = url.toLocalFile();

        std::unique_ptr<FileLoadOptions> file_options(new FileLoadOptions);
        file_options->copyBaseFrom(options);

        auto given_file_options = dynamic_cast<const FileLoadOptions*>(&options);
        if (given_file_options) {
            file_options->forceNew = given_file_options->forceNew;
        } else {
            qWarning() << "'options' argument for deviceFromUrl function should be of FileLoadOptions class";
        }

        // if we are loading only range of device, we cannot make it resizeable.
        if (file_options->rangeLoad) {
            file_options->freezeSize = true;
        }

        if (!QFileInfo(local_file_path).exists() && !file_options->forceNew) {
            throw DeviceError(QString("file %1 does not exist").arg(local_file_path));
        }

        device = std::shared_ptr<FileDevice>(new FileDevice(local_file_path, file_options.release()));
    } else if (url.scheme().toLower() == "microdata") {
        std::unique_ptr<BufferLoadOptions> buffer_options(new BufferLoadOptions());
        buffer_options->copyBaseFrom(options);

        auto given_buffer_options = dynamic_cast<const BufferLoadOptions*>(&options);
        if (given_buffer_options) {
            buffer_options->data = given_buffer_options->data;
        } else {
            qWarning() << "buffer cannot be loaded: 'options' argument to deviceFromUrl should be of BufferLoadOptions class";
        }

        if (buffer_options->memoryLoad) {
            // memoryLoad flag has no meaning for buffer: it always loaded into memory.
            buffer_options->memoryLoad = false;
        }

        // if we are loading only range of device, we cannot make it resizeable.
        if (buffer_options->rangeLoad) {
            buffer_options->freezeSize = true;
        }

        device = std::shared_ptr<BufferDevice>(new BufferDevice(buffer_options.release()));

        // disable cache for buffers
        device->setCacheSize(0);
    } else {
        throw DeviceError(QString("unknown scheme for device URL: %1").arg(url.toString()));
    }

    if (device && device->getLoadOptions().memoryLoad) {
        // note that even memory-loaded device will re-read its data from underlying device after cache
        // is invalidated (for example, after writing some data)
        device->setCacheSize(device->getLength());
        device->_encache(0, false);
    }

    QMutexLocker locker(&_allDevicesMutex);
    _allDevices.append(device.get());
    return device;
}

std::shared_ptr<BufferDevice> deviceFromData(const QByteArray &data, const BufferLoadOptions &options) {
    BufferLoadOptions buffer_load_options;
    buffer_load_options.copyBaseFrom(options);
    buffer_load_options.data = data;
    return std::dynamic_pointer_cast<BufferDevice>(deviceFromUrl(QUrl("microdata://"), buffer_load_options));
}

std::shared_ptr<FileDevice> deviceFromFile(const QString &filename, const FileLoadOptions &options) {
    return std::dynamic_pointer_cast<FileDevice>(deviceFromUrl(QUrl::fromLocalFile(filename), options));
}
