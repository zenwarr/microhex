#ifndef DEVICES_H
#define DEVICES_H

#include <exception>
#include <QObject>
#include <QUrl>
#include <QByteArray>
#include <QList>
#include <QIODevice>
#include <QFile>


class Document;
class DeviceSpan;
class AbstractSaver;
class AbstractSpan;


class OutOfBoundsError : public std::exception {
public:
    OutOfBoundsError() : std::exception() {

    }
};


class IOError : public std::exception {
public:
    IOError(const QString &desc) : std::exception(), _desc(desc) {

    }

private:
    const QString &_desc;
};


class ReadOnlyError : public IOError {
public:
    ReadOnlyError() : IOError("operation is not allowed: read only") {

    }
};


class FrozenSizeError : public IOError {
public:
    FrozenSizeError() : IOError("operation is not allowed: size is fixed") {

    }
};


class LoadOptions {
public:
    LoadOptions() : readOnly(false) {

    }
    virtual ~LoadOptions() { }

    bool readOnly;
};


class FileLoadOptions : public LoadOptions {
public:
    FileLoadOptions() : LoadOptions(), rangeStart(0), rangeLength(-1), memoryLoad(false), freezeSize(false),
        forceNew(false) {

    }

    qulonglong rangeStart, rangeLength;
    bool memoryLoad, freezeSize, forceNew;
};


class AbstractDevice : public QObject {
    Q_OBJECT
    friend class DeviceSpan;
public:
    AbstractDevice(const QUrl &url=QUrl(), const LoadOptions &options=LoadOptions());
    virtual ~AbstractDevice();

    const QUrl &url()const { return _url; }
    virtual bool fixedSize()const = 0;
    virtual qulonglong length()const = 0;
    virtual bool readOnly()const;
    const LoadOptions &loadOptions()const { return _loadOptions; }

    QByteArray read(qulonglong position, qulonglong length)const;
    QByteArray readAll()const;
    qulonglong write(qulonglong position, const QByteArray &data);
    virtual void resize(qulonglong new_size) = 0;
    virtual AbstractSaver *createSaver(Document *editor, AbstractDevice *read_device);

    qulonglong cacheSize()const { return _cacheSize; }
    void setCacheSize(qulonglong size);

    QList<DeviceSpan*> spans()const { return _spans; }

    DeviceSpan *createSpan(qulonglong offset, qulonglong length);

protected:
    virtual QByteArray _read(qulonglong position, qulonglong length)const = 0;
    virtual qulonglong _write(qulonglong position, const QByteArray &data) = 0;
    void _removeSpan(DeviceSpan *span)const;
    void _addSpan(DeviceSpan *span)const;

    void _encache(qulonglong, bool)const;

private:
    QUrl _url;
    mutable QByteArray _cache;
    mutable qulonglong _cacheStart;
    qulonglong _cacheSize;
    qulonglong _cacheBoundary;
    LoadOptions _loadOptions;
    mutable QList<DeviceSpan*> _spans;
};


class AbstractSaver : public QObject {
public:
    AbstractSaver() { }
    virtual ~AbstractSaver() { }

    virtual void begin() = 0;
    virtual void putSpan(AbstractSpan *span) = 0;
    virtual void fail() { }
    virtual void complete() { }
};


class StandardSaver : public AbstractSaver {
public:
    StandardSaver(AbstractDevice *readDevice, AbstractDevice *writeDevice);
    void begin();
    void putSpan(AbstractSpan *span);

protected:
    qulonglong _position;
    AbstractDevice *_readDevice, *_writeDevice;
};


class QtProxyDevice : public AbstractDevice {
    Q_OBJECT
public:
    QtProxyDevice(const QUrl &url=QUrl(), const LoadOptions &options=LoadOptions());

    qulonglong length()const;
    const QIODevice *qdevice()const { return _qdevice; }
    QIODevice *qdevice() { return _qdevice; }

private slots:
    void _onDeviceAboutToClose();

protected:
    QIODevice *_qdevice;
    mutable bool _deviceClosed;

    void _ensureOpened()const;
    void _setQDevice(QIODevice *device);
    QByteArray _read(qulonglong position, qulonglong length)const;
    qulonglong _write(qulonglong position, const QByteArray &data);
};


class FileDevice : public QtProxyDevice {
    Q_OBJECT
public:
    FileDevice(const QString &filename, const FileLoadOptions &options=FileLoadOptions());

    bool fixedSize() const;
    void resize(qulonglong new_size);
    AbstractSaver *createSaver(Document *editor, AbstractDevice *read_device);
    const FileLoadOptions &fileLoadOptions()const { return _fileLoadOptions; }

private:
    FileLoadOptions _fileLoadOptions;
};


class BufferDevice : public QtProxyDevice {
    Q_OBJECT
public:
    BufferDevice(QByteArray *array, const LoadOptions &loadOptions=LoadOptions());

    bool fixedSize() const;
    void resize(qulonglong new_size);
};

#endif // DEVICES_H
