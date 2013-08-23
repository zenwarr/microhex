%Module documents

%Import QtCore/QtCoremod.sip
%Import QtGui/QtGuimod.sip


%Exception std::exception(SIP_Exception) {
%TypeHeaderCode
    #include "base.h"
    #include "devices.h"
    #include "sharedwrap.h"
    #include <new>
    #include <stdexcept>
%End

%RaiseCode
    SIP_BLOCK_THREADS
    if (dynamic_cast<const std::bad_alloc *>(&sipExceptionRef)) {
        PyErr_NoMemory();
    } else if (dynamic_cast<const std::out_of_range *>(&sipExceptionRef) ||
               dynamic_cast<const OutOfBoundsError*>(&sipExceptionRef)) {
        PyErr_SetString(PyExc_IndexError, sipExceptionRef.what());
    } else if (dynamic_cast<const std::overflow_error *>(&sipExceptionRef)) {
        PyErr_SetString(PyExc_OverflowError, sipExceptionRef.what());
    } else if (dynamic_cast<const NullPointerError *>(&sipExceptionRef)) {
        PyErr_SetString(PyExc_AttributeError, "object is None");
    } else {
        PyErr_SetString(PyExc_RuntimeError, sipExceptionRef.what());
    }
    SIP_UNBLOCK_THREADS
%End
};


class LoadOptions {
    %TypeHeaderCode
    #include "devices.h"
    %End
public:
    LoadOptions();
    virtual ~LoadOptions();

    bool readOnly;
    bool rangeLoad;
    bool memoryLoad;
    bool freezeSize;
    qulonglong rangeStart;
    qulonglong rangeLength;
};


class FileLoadOptions : public LoadOptions {
    %TypeHeaderCode
    #include "devices.h"
    %End
public:
    FileLoadOptions();

    bool forceNew;
};


class BufferLoadOptions : public LoadOptions {
    %TypeHeaderCode
    #include "devices.h"
    %End

public:
    BufferLoadOptions();

    QByteArray data;
};


class WrappedBase {
    %TypeHeaderCode
    #include "sharedwrap.h"
    %End
public:
    bool isNull()const;
    bool isClone(const WrappedBase &other)const;

private:
    WrappedBase();
    ~WrappedBase();
};


class SharedReadWriteLock : public WrappedBase /PyName=ReadWriteLock/ {
    %TypeHeaderCode
    #include "sharedwrap.h"
    %End
public:
    SharedReadWriteLock();

    void lockForRead() throw (std::exception);
    void lockForWrite() throw (std::exception);
    bool tryLockForRead(int timeout=-1) throw (std::exception);
    bool tryLockForWrite(int timeout=-1) throw (std::exception);
    void unlockRead() throw (std::exception);
    void unlockWrite() throw (std::exception);
};


class SharedAbstractSpan : public WrappedBase /PyName=AbstractSpan/ {
    %TypeHeaderCode
    #include "sharedwrap.h"
    %End
public:
    qulonglong getLength()const throw (std::exception);
    QByteArray read(qulonglong offset, qulonglong length)const throw (std::exception);

    %Property(name=length, get=getLength)

private:
    SharedAbstractSpan();
};


class SharedDataSpan : public SharedAbstractSpan /PyName=DataSpan/ {
    %TypeHeaderCode
    #include "sharedwrap.h"
    %End
public:
    SharedDataSpan(const QByteArray &data) throw (std::exception);
};


class SharedFillSpan : public SharedAbstractSpan /PyName=FillSpan/ {
    %TypeHeaderCode
    #include "sharedwrap.h"
    %End
public:
    SharedFillSpan(qulonglong repeat_count, char fill_byte) throw (std::exception);
};


class SharedAbstractDevice : public WrappedBase /PyName=AbstractDevice/ {
    %TypeHeaderCode
    #include "sharedwrap.h"
    %End
public:
    SharedAbstractDevice() throw (std::exception);

    QUrl getUrl()const throw (std::exception);
    SharedReadWriteLock getLock()const throw (std::exception);
    bool isFixedSize()const throw (std::exception);
    bool isReadOnly()const throw (std::exception);
    qulonglong getLength()const throw (std::exception);
    const LoadOptions &getLoadOptions()const throw (std::exception);

    QByteArray read(qulonglong position, qulonglong length)const throw (std::exception);
    QByteArray readAll()const throw (std::exception);
    qulonglong write(qulonglong position, const QByteArray &data) throw (std::exception);
    void resize(qulonglong new_size) throw (std::exception);

    qulonglong getCacheSize()const throw (std::exception);
    void setCacheSize(qulonglong new_cache_size) throw (std::exception);

    %Property(name=length, get=getLength)
    %Property(name=cacheSize, get=getCacheSize, set=setCacheSize)
    %Property(name=loadOptions, get=getLoadOptions)
    %Property(name=readOnly, get=isReadOnly)
    %Property(name=fixedSize, get=isFixedSize)
    %Property(name=lock, get=getLock)
    %Property(name=url, get=getUrl)
};


class SharedDeviceSpan : public SharedAbstractSpan /PyName=DeviceSpan/ {
    %TypeHeaderCode
    #include "sharedwrap.h"
    %End
public:
    SharedDeviceSpan(const SharedAbstractDevice &device, qulonglong device_offset, qulonglong length) throw (std::exception);
};


class SharedFileDevice : public SharedAbstractDevice /PyName=FileDevice/ {
    %TypeHeaderCode
    #include "sharedwrap.h"
    %End
public:

private:
    SharedFileDevice();
};


class SharedBufferDevice : public SharedAbstractDevice /PyName=BufferDevice/ {
    %TypeHeaderCode
    #include "sharedwrap.h"
    %End
public:

private:
    SharedBufferDevice();
};


class SharedSpanChain : public WrappedBase /PyName=SpanChain/ {
    %TypeHeaderCode
    #include "sharedwrap.h"
    %End
public:
    qulonglong getLength()const throw (std::exception);
    SharedReadWriteLock getLock()const throw (std::exception);

    QList<SharedAbstractSpan> getSpans()const throw (std::exception);
    void setSpans(const QList<SharedAbstractSpan> &spans) throw (std::exception);
    void clear() throw (std::exception);

    QByteArray read(qulonglong offset, qulonglong length)const throw (std::exception);
    QByteArray readAll()const throw (std::exception);
    QList<SharedAbstractSpan> spansInRange(qulonglong offset, qulonglong length, qulonglong *left_offset /Out/ = nullptr,
                          qulonglong *right_offset /Out/ = nullptr)const throw (std::exception);
    SharedAbstractSpan spanAtOffset(qulonglong offset, qulonglong *span_offset /Out/ = nullptr)const throw (std::exception);
    QList<SharedAbstractSpan> takeSpans(qulonglong offset, qulonglong length) throw (std::exception);
    void splitSpans(qulonglong offset) throw (std::exception);

    void insertSpan(qulonglong offset, SharedAbstractSpan &span) throw (std::exception);
    void insertChain(qulonglong offset, SharedSpanChain &chain) throw (std::exception);
    void remove(qulonglong offset, qulonglong length) throw (std::exception);

    SharedSpanChain takeChain(qulonglong offset, qulonglong length)const throw (std::exception);
    SharedSpanChain exportRange(qulonglong offset, qulonglong length, int ram_limit=-1)const throw (std::exception);

    %Property(name=length, get=getLength)
    %Property(name=lock, get=getLock)
    %Property(name=spans, get=getSpans, set=setSpans)
};


class SharedDocument : public QObject, public WrappedBase /PyName=Document/ {
    %TypeHeaderCode
    #include "sharedwrap.h"
    %End
public:
    SharedDocument(const SharedAbstractDevice &device) throw (std::exception);
    SharedDocument() throw (std::exception);

    SharedAbstractDevice getDevice()const throw (std::exception);
    SharedReadWriteLock getLock()const throw (std::exception);
    QUrl getUrl()const throw (std::exception);
    qulonglong getLength()const throw (std::exception);
    bool isFixedSize()const throw (std::exception);
    void setFixedSize(bool f) throw (std::exception);
    bool isReadOnly()const throw (std::exception);
    void setReadOnly(bool r) throw (std::exception);

    QByteArray read(qulonglong position, qulonglong length)const throw (std::exception);
    QByteArray readAll()const throw (std::exception);

    void insertSpan(qulonglong position, const SharedAbstractSpan &span, char fill_byte=0) throw (std::exception);
    void insertChain(qulonglong position, const SharedSpanChain &chain, char fill_byte=0) throw (std::exception);
    void appendSpan(const SharedAbstractSpan &span) throw (std::exception);
    void appendChain(const SharedSpanChain &chain) throw (std::exception);
    void writeSpan(qulonglong position, const SharedAbstractSpan &span, char fill_byte=0) throw (std::exception);
    void writeChain(qulonglong position, const SharedSpanChain &chain, char fill_byte=0) throw (std::exception);
    void remove(qulonglong position, qulonglong length) throw (std::exception);
    void clear() throw (std::exception);

    bool isModified()const throw (std::exception);
    bool isRangeModified(qulonglong position, qulonglong length)const throw (std::exception);

    void undo() throw (std::exception);
    void redo(int branch_id=-1) throw (std::exception);
    void beginComplexAction(const QString &title=QString()) throw (std::exception);
    void endComplexAction() throw (std::exception);
    bool canUndo()const throw (std::exception);
    bool canRedo()const throw (std::exception);
    QList<int> getAlternativeBranchesIds()const throw (std::exception);

    void save(SharedAbstractDevice *write_device=nullptr, bool switch_devices=false) throw (std::exception);
    SharedSpanChain exportRange(qulonglong position, qulonglong length, int ram_limit=-1)const throw (std::exception);

signals:
    void dataChanged(qulonglong, qulonglong);
    void bytesInserted(qulonglong, qulonglong);
    void bytesRemoved(qulonglong, qulonglong);
    void resized(qulonglong);
    void canUndoChanged(bool);
    void canRedoChanged(bool);
    void isModifiedChanged(bool);
    void urlChanged(const QUrl &);
    void readOnlyChanged(bool);
    void fixedSizeChanged(bool);

    %Property(name=length, get=getLength)
    %Property(name=lock, get=getLock)
    %Property(name=fixedSize, get=isFixedSize, set=setFixedSize)
    %Property(name=readOnly, get=isReadOnly, set=setReadOnly)
    %Property(name=device, get=getDevice)
    %Property(name=url, get=getUrl)
    %Property(name=modified, get=isModified)
};


class SharedBinaryFinder : public WrappedBase /PyName=BinaryFinder/ {
    %TypeHeaderCode
    #include "sharedwrap.h"
    %End
public:
    SharedBinaryFinder(const SharedDocument &document, const QByteArray &findWhat);

    qulonglong findNext(qulonglong from_position, qulonglong limit, bool *ok /Out/);
    qulonglong findPrevious(qulonglong from_position, qulonglong limit, bool *ok /Out/);
};


%ModuleCode
#include "sharedwrap.h"
%End

SharedAbstractDevice sharedDeviceFromUrl(const QUrl &url, const LoadOptions &options) throw (std::exception) /PyName=deviceFromUrl/;
SharedFileDevice sharedDeviceFromFile(const QString &file, const FileLoadOptions &options=FileLoadOptions()) throw (std::exception) /PyName=deviceFromFile/;
SharedBufferDevice sharedDeviceFromData(const QByteArray &data, const BufferLoadOptions &options=BufferLoadOptions()) throw (std::exception) /PyName=deviceFromData/;

namespace Clipboard {

%TypeHeaderCode
#include "sharedwrap.h"
%End

void sharedSetData(const SharedDocument &document, qulonglong position, qulonglong length) throw (std::exception) /PyName=setData/;
SharedSpanChain sharedGetData() throw (std::exception) /PyName=getData/;
bool sharedHasMicrohexData() throw (std::exception) /PyName=hasMicrohexData/;

};
