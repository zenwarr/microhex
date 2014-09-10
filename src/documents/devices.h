#ifndef DEVICES_H
#define DEVICES_H

#include <exception>
#include <memory>
#include <QObject>
#include <QUrl>
#include <QByteArray>
#include <QList>
#include <QIODevice>
#include <QFile>
#include "readwritelock.h"
#include "base.h"


class Document;
class PrimitiveDeviceSpan;
class DeviceSpan;
class AbstractSaver;
class AbstractSpan;


class OutOfBoundsError : public BaseException {
public:
    OutOfBoundsError() : BaseException("index or offset is out of range") { }
};


class DeviceError : public BaseException {
public:
    DeviceError(const QString &desc) : BaseException(desc) { }
};


class ReadOnlyError : public DeviceError {
public:
    ReadOnlyError() : DeviceError("operation is not allowed: read only") { }
};


class FrozenSizeError : public DeviceError {
public:
    FrozenSizeError() : DeviceError("operation is not allowed: size is fixed") { }
};


class LoadOptions {
public:
    LoadOptions() : readOnly(), rangeLoad(), memoryLoad(), freezeSize(), rangeStart(), rangeLength() {

    }
    virtual ~LoadOptions() { }

    bool readOnly, rangeLoad, memoryLoad, freezeSize;
    qulonglong rangeStart, rangeLength;

    void copyBaseFrom(const LoadOptions &options);
};


class FileLoadOptions : public LoadOptions {
public:
    FileLoadOptions() : LoadOptions(), forceNew(false) {

    }

    bool forceNew;
};


class BufferLoadOptions : public LoadOptions {
public:
    BufferLoadOptions() { }

    QByteArray data;
};


class AbstractDevice : public QObject, public std::enable_shared_from_this<AbstractDevice> {
    Q_OBJECT
    friend class PrimitiveDeviceSpan;
    friend std::shared_ptr<AbstractDevice> deviceFromUrl(const QUrl &url, const LoadOptions &options);
public:
    virtual ~AbstractDevice();

    std::shared_ptr<ReadWriteLock> getLock()const { return _lock; }

    const QUrl &getUrl()const { return _url; }
    virtual bool isFixedSize()const = 0;
    virtual qulonglong getLength()const;
    virtual bool isReadOnly()const;
    const LoadOptions &getLoadOptions()const { return *_loadOptions; }
    virtual bool isSharedResource()const = 0;

    QByteArray read(qulonglong position, qulonglong length)const;
    QByteArray readAll()const;
    qulonglong write(qulonglong position, const QByteArray &data);
    virtual void resize(qulonglong new_size);
    virtual std::shared_ptr<AbstractSaver> createSaver(const std::shared_ptr<Document> &editor,
                                                       const std::shared_ptr<AbstractDevice> &read_device);

    qulonglong getCacheSize()const { return _cacheSize; }
    void setCacheSize(qulonglong size);

    QList<std::shared_ptr<PrimitiveDeviceSpan>> getSpans()const;
    std::shared_ptr<PrimitiveDeviceSpan> createSpan(qulonglong position, qulonglong length);

signals:
    void readOnlyChanged(bool read_only)const;

protected:
    AbstractDevice(const QUrl &url, LoadOptions *options);

    virtual QByteArray _read(qulonglong position, qulonglong length)const = 0;
    virtual qulonglong _write(qulonglong position, const QByteArray &data) = 0;
    virtual qulonglong _totalLength()const = 0;
    virtual void _resize(qulonglong) = 0;
    void _removeSpan(PrimitiveDeviceSpan *span);

    void _encache(qulonglong, bool)const;

    std::unique_ptr<LoadOptions> _loadOptions;

private:
    QUrl _url;
    mutable QByteArray _cache;
    mutable qulonglong _cacheStart;
    qulonglong _cacheSize;
    qulonglong _cacheBoundary;
    mutable QList<PrimitiveDeviceSpan*> _spans;
    std::shared_ptr<ReadWriteLock> _lock;
};


class AbstractSaver : public QObject {
public:
    AbstractSaver() { }
    virtual ~AbstractSaver() { }

    virtual void begin() = 0;
    virtual void putSpan(const std::shared_ptr<const AbstractSpan> &span) = 0;
    virtual void fail() { } // should never throw!
    virtual void complete() { }
};


class StandardSaver : public AbstractSaver {
public:
    StandardSaver(const std::shared_ptr<Document> &document, const std::shared_ptr<AbstractDevice> &readDevice,
                  const std::shared_ptr<AbstractDevice> &writeDevice);
    void begin();
    void putSpan(const std::shared_ptr<const AbstractSpan> &span);

protected:
    qulonglong _position;
    std::shared_ptr<AbstractDevice> _readDevice, _writeDevice;
    std::shared_ptr<Document> _document;
};


class QtProxyDevice : public AbstractDevice {
    Q_OBJECT
public:
    const std::shared_ptr<QIODevice> &getQDevice()const { return _qdevice; }

private slots:
    void _onDeviceAboutToClose();

protected:
    std::shared_ptr<QIODevice> _qdevice;
    mutable bool _deviceClosed;

    QtProxyDevice(const QUrl &url, LoadOptions *options);
    void _ensureOpened()const;
    void _setQDevice(const std::shared_ptr<QIODevice> &device);
    QByteArray _read(qulonglong position, qulonglong length)const;
    qulonglong _write(qulonglong position, const QByteArray &data);
    qulonglong _totalLength()const;
};


class FileDevice : public QtProxyDevice {
    Q_OBJECT
    friend std::shared_ptr<AbstractDevice> deviceFromUrl(const QUrl &url, const LoadOptions &options=LoadOptions());
public:
    bool isFixedSize() const;
    std::shared_ptr<AbstractSaver> createSaver(const std::shared_ptr<Document> &editor,
                                               const std::shared_ptr<AbstractDevice> &read_device);
    const FileLoadOptions &getFileLoadOptions()const;
    bool isSharedResource()const { return true; }

protected:
    FileDevice(const QString &filename, FileLoadOptions *options);

    void _resize(qulonglong new_size);
};


class BufferDevice : public QtProxyDevice {
    Q_OBJECT
    friend std::shared_ptr<AbstractDevice> deviceFromUrl(const QUrl &url, const LoadOptions &options);
public:
    bool isFixedSize() const;
    bool isSharedResource()const { return false; }
    const BufferLoadOptions &getBufferLoadOptions()const;

protected:
    BufferDevice(BufferLoadOptions *loadOptions);

    void _resize(qulonglong new_size);
};


std::shared_ptr<AbstractDevice> deviceFromUrl(const QUrl &url, const LoadOptions &options);
std::shared_ptr<FileDevice> deviceFromFile(const QString &file, const FileLoadOptions &options=FileLoadOptions());
std::shared_ptr<BufferDevice> deviceFromData(const QByteArray &data, const BufferLoadOptions &options=BufferLoadOptions());


#endif // DEVICES_H
