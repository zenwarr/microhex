%Module documents

%Import QtCore/QtCoremod.sip


%MappedType QPair<AbstractSpan*, AbstractSpan*> {
    %TypeHeaderCode
    #include <QPair>
    #include "spans.h"
    %End

    %ConvertFromTypeCode
    PyObject *tuple = PyTuple_New(2);
    if (!tuple) {
        return nullptr;
    }

    PyTuple_SET_ITEM(tuple, 0, sipConvertFromType(sipCpp->first, sipType_AbstractSpan, sipTransferObj));
    PyTuple_SET_ITEM(tuple, 0, sipConvertFromType(sipCpp->second, sipType_AbstractSpan, sipTransferObj));

    return tuple;
    %End

    %ConvertToTypeCode
    if (!sipIsErr) {
        return PyTuple_Size(sipPy) == 2 &&
                sipCanConvertToType(PyTuple_GET_ITEM(sipPy, 0), sipType_AbstractSpan, SIP_NOT_NONE) &&
                sipCanConvertToType(PyTuple_GET_ITEM(sipPy, 1), sipType_AbstractSpan, SIP_NOT_NONE);
    }

    int state;
    AbstractSpan *f = reinterpret_cast<AbstractSpan*>(sipConvertToType(PyTuple_GET_ITEM(sipPy, 0),
                                                                       sipType_AbstractSpan, sipTransferObj, SIP_NOT_NONE,
                                                                       &state, sipIsErr));
    AbstractSpan *s = reinterpret_cast<AbstractSpan*>(sipConvertToType(PyTuple_GET_ITEM(sipPy, 1),
                                                                       sipType_AbstractSpan, sipTransferObj, SIP_NOT_NONE,
                                                                       &state, sipIsErr));
    if (!*sipIsErr) {
        *sipCppPtr = new QPair<AbstractSpan*, AbstractSpan*>(f, s);
        return sipGetState(sipTransferObj);
    }

    return 0;
    %End
};


class AbstractSpan : public QObject {
    %TypeHeaderCode
    #include "spans.h"
    %End
public:
    AbstractSpan();
    ~AbstractSpan();

    virtual qulonglong length()const = 0;
    virtual QByteArray read(qulonglong offset, qulonglong length)const = 0;
    virtual QPair<AbstractSpan*, AbstractSpan*> split(qulonglong offset)const = 0;

    virtual AbstractSpan *clone()const = 0;
    SpanChain *parentChain()const;

    qulonglong savepoint;

protected:
    bool _isRangeValid(qulonglong offset, qulonglong size)const;

private:
    AbstractSpan(const AbstractSpan &);
    AbstractSpan &operator=(const AbstractSpan &);
};


class DataSpan : public AbstractSpan {
    %TypeHeaderCode
    #include "spans.h"
    %End
public:
    DataSpan(const QByteArray &data);

    qulonglong length()const;
    QByteArray read(qulonglong offset, qulonglong length)const;
    AbstractSpan* clone()const;
    QPair<AbstractSpan*, AbstractSpan*> split(qulonglong offset)const;
};


class FillSpan : public AbstractSpan {
    %TypeHeaderCode
    #include "spans.h"
    %End
public:
    FillSpan(char fill_byte, int repeat_count);

    qulonglong length()const;
    QByteArray read(qulonglong offset, qulonglong length) const;
    AbstractSpan* clone()const;
    QPair<AbstractSpan*, AbstractSpan*> split(qulonglong offset)const;
};


class DeviceSpan : public AbstractSpan {
    %TypeHeaderCode
    #include "spans.h"
    %End
public:
    DeviceSpan(const AbstractDevice *device, qulonglong deviceOffset, qulonglong length);
    ~DeviceSpan();

    qulonglong length()const;
    QByteArray read(qulonglong offset, qulonglong length) const;
    AbstractSpan* clone()const;
    const AbstractDevice *device()const;
    qulonglong deviceOffset()const;
    QPair<AbstractSpan*, AbstractSpan*> split(qulonglong offset)const;
};


class SpanChain : public QObject {
    %TypeHeaderCode
    #include "chain.h"
    %End
public:
    SpanChain(const QList<AbstractSpan*> &spans=QList<AbstractSpan*>());
    ~SpanChain();

    qulonglong length()const;

    const QList<AbstractSpan*> &spans()const;
    void setSpans(const QList<AbstractSpan*> &spans);
    void clear();

    QByteArray read(qulonglong offset, qulonglong length)const;
    QByteArray readAll()const;
    QList<AbstractSpan*> spansInRange(qulonglong offset, qulonglong length, qulonglong *left_offset=0,
                          qulonglong *right_offset=0)const;
    int findSpanIndex(qulonglong offset, qulonglong *span_offset=0)const;
    AbstractSpan* spanAtOffset(qulonglong offset, qulonglong *span_offset=0)const;
    QList<AbstractSpan*> takeSpans(qulonglong offset, qulonglong length);
    void splitSpans(qulonglong offset);

    void insertSpan(qulonglong offset, AbstractSpan *span);
    void insertChain(qulonglong offset, SpanChain *chain);
    void remove(qulonglong offset, qulonglong length);
};


class LoadOptions {
    %TypeHeaderCode
    #include "devices.h"
    %End
public:
    LoadOptions();
    virtual ~LoadOptions();

    bool readOnly;
};


class FileLoadOptions : public LoadOptions {
    %TypeHeaderCode
    #include "devices.h"
    %End
public:
    FileLoadOptions();

    qulonglong rangeStart;
    qulonglong rangeLength;
    bool memoryLoad;
    bool freezeSize;
    bool forceNew;
};


class AbstractDevice : public QObject {
    %TypeHeaderCode
    #include "devices.h"
    %End
public:
    AbstractDevice(const QUrl &url=QUrl(), const LoadOptions &options=LoadOptions());
    virtual ~AbstractDevice();

    const QUrl &url()const;
    virtual bool fixedSize()const = 0;
    virtual qulonglong length()const = 0;
    virtual bool readOnly()const;
    const LoadOptions &loadOptions()const;

    QByteArray read(qulonglong position, qulonglong length)const;
    QByteArray readAll()const;
    qulonglong write(qulonglong position, const QByteArray &data);
    virtual void resize(qulonglong new_size) = 0;

    qulonglong cacheSize()const;
    void setCacheSize(qulonglong size);

    QList<DeviceSpan*> spans()const;

    DeviceSpan *createSpan(qulonglong offset, qulonglong length);

protected:
    virtual QByteArray _read(qulonglong position, qulonglong length)const = 0;
    virtual qulonglong _write(qulonglong position, const QByteArray &data) = 0;
    void _removeSpan(DeviceSpan *span)const;
    void _addSpan(DeviceSpan *span)const;
    void _encache(qulonglong, bool)const;
};


class QtProxyDevice : public AbstractDevice {
    %TypeHeaderCode
    #include "devices.h"
    %End
public:
    QtProxyDevice(const QUrl &url=QUrl(), const LoadOptions &options=LoadOptions());

    qulonglong length()const;
    QIODevice *qdevice();

protected:
    virtual QByteArray _read(qulonglong position, qulonglong length)const;
    virtual qulonglong _write(qulonglong position, const QByteArray &data);
};


class FileDevice : public QtProxyDevice {
    %TypeHeaderCode
    #include "devices.h"
    %End
public:
    FileDevice(const QString &filename, const FileLoadOptions &options=FileLoadOptions());

    bool fixedSize() const;
    void resize(qulonglong new_size);
};


class BufferDevice : public QtProxyDevice {
    %TypeHeaderCode
    #include "devices.h"
    %End
public:
    BufferDevice(QByteArray *array, const LoadOptions &loadOptions=LoadOptions());

    bool fixedSize() const;
    void resize(qulonglong new_size);
};


class Document : public QObject {
    %TypeHeaderCode
    #include "document.h"
    %End
public:
    Document(AbstractDevice *device=nullptr);
    ~Document();

    AbstractDevice *device()const;
    QUrl url()const;
    qulonglong length()const;
    bool fixedSize()const;
    void setFixedSize(bool fixed_size);
    bool readOnly()const;
    void setReadOnly(bool read_only);

    QByteArray read(qulonglong position, qulonglong length)const;
    QByteArray readAll()const;

    void insertSpan(qulonglong position, AbstractSpan *span, char fill_byte=0);
    void insertChain(qulonglong position, SpanChain *chain, char fill_byte=0);
    void appendSpan(AbstractSpan *span);
    void appendChain(SpanChain *chain);
    void writeSpan(qulonglong position, AbstractSpan *span, char fill_byte=0);
    void writeChain(qulonglong position, SpanChain *chain, char fill_byte=0);
    void remove(qulonglong position, qulonglong length);
    void clear();

    bool isModified()const;
    bool isRangeModified(qulonglong position, qulonglong length)const;

    void undo();
    void redo(int branch_id=-1);
    void addAction(AbstractUndoAction *action);
    void beginComplexAction(const QString &title=QString());
    void endComplexAction();
    bool canUndo()const;
    bool canRedo()const;
    QList<int> alternativeBranchesIds()const;

    void save(AbstractDevice *write_device, bool switch_devices=false);
    bool checkCanQuickSave()const;

signals:
    void dataChanged(qulonglong, qulonglong);
    void bytesInserted(qulonglong, qulonglong);
    void bytesRemoved(qulonglong, qulonglong);
    void resized(qulonglong);
    void canUndoChanged(bool);
    void canRedoChanged(bool);
    void isModifiedChanged(bool);
    void urlChanged(const QUrl &);
};


class AbstractUndoAction : public QObject {
    %TypeHeaderCode
    #include "document.h"
    %End
public:
    AbstractUndoAction(Document *document, const QString &title=QString());
    virtual ~AbstractUndoAction();

    Document *document();
    QString title()const;

    AbstractUndoAction *parentAction()const;

    virtual void undo() = 0;
    virtual void redo() = 0;
};


class ReadWriteLock {
%TypeHeaderCode
#include "readwritelock.h"
%End
public:
    ReadWriteLock();
    ~ReadWriteLock();

    void lockForRead();
    void lockForWrite();
    bool tryLockForRead(int timeout=-1);
    bool tryLockForWrite(int timeout=-1);
    void unlockRead();
    void unlockWrite();

private:
    ReadWriteLock(const ReadWriteLock &);
    ReadWriteLock &operator=(const ReadWriteLock&);
};
