#ifndef M_SHARED_WRAP_H
#define M_SHARED_WRAP_H

#include "spans.h"
#include "devices.h"
#include "chain.h"
#include "document.h"
#include "matcher.h"
#include "clipboard.h"
#include "base.h"

class NullPointerError : public BaseException {
public:
    NullPointerError() : BaseException(QString()) {

    }
};

class WrappedBase {
public:
    virtual ~WrappedBase() { }

    virtual bool isNull()const {
        return !rawPointer();
    }

    virtual bool isClone(const WrappedBase &other)const {
        return rawPointer() == other.rawPointer();
    }

protected:
    virtual void *rawPointer()const = 0;
};

template<typename T> class SharedWrapBase : public WrappedBase {
public:
    SharedWrapBase(const std::shared_ptr<T> &wrapped) : _wrapped(wrapped) {

    }

    virtual ~SharedWrapBase() {

    }

    const std::shared_ptr<T> &wrapped()const {
        if (isNull()) {
            throw NullPointerError();
        }
        return _wrapped;
    }

    template<typename X> std::shared_ptr<X> wrapped()const {
        if (isNull()) {
            throw NullPointerError();
        }
        return std::dynamic_pointer_cast<X>(_wrapped);
    }

protected:
    std::shared_ptr<T> _wrapped;

    void *rawPointer()const { return (void*)_wrapped.get(); }
};


class SharedReadWriteLock : public SharedWrapBase<ReadWriteLock> {
public:
    SharedReadWriteLock(const std::shared_ptr<ReadWriteLock> &wrapped) : SharedWrapBase(wrapped) {

    }

    SharedReadWriteLock() : SharedWrapBase(std::make_shared<ReadWriteLock>()) {

    }

    void lockForRead() { wrapped()->lockForRead(); }
    void lockForWrite() { wrapped()->lockForWrite(); }
    bool tryLockForRead(int timeout=-1) { return wrapped()->tryLockForRead(timeout); }
    bool tryLockForWrite(int timeout=-1) { return wrapped()->tryLockForWrite(timeout); }
    void unlockRead() { wrapped()->unlockRead(); }
    void unlockWrite() { wrapped()->unlockWrite(); }
};


class SharedAbstractSpan : public SharedWrapBase<AbstractSpan> {
public:
    SharedAbstractSpan(const std::shared_ptr<AbstractSpan> &wrapped) : SharedWrapBase(wrapped) {

    }

    SharedAbstractSpan() : SharedWrapBase(nullptr) {

    }

    qulonglong getLength()const { return _wrapped->getLength(); }
    QByteArray read(qulonglong offset, qulonglong length)const { return _wrapped->read(offset, length); }
};


class SharedDataSpan : public SharedAbstractSpan {
public:
    SharedDataSpan(const std::shared_ptr<DataSpan> &wrapped) : SharedAbstractSpan(wrapped) {

    }

    SharedDataSpan(const QByteArray &data) : SharedAbstractSpan(std::make_shared<DataSpan>(data)) {

    }
};


class SharedFillSpan : public SharedAbstractSpan {
public:
    SharedFillSpan(const std::shared_ptr<FillSpan> &wrapped) : SharedAbstractSpan(wrapped) {

    }

    SharedFillSpan(qulonglong repeat_count, char fill_byte)
        : SharedAbstractSpan(std::make_shared<FillSpan>(repeat_count, fill_byte)) {

    }
};


class SharedAbstractDevice : public SharedWrapBase<AbstractDevice> {
public:
    SharedAbstractDevice(const std::shared_ptr<AbstractDevice> &wrapped) : SharedWrapBase(wrapped) {

    }

    SharedAbstractDevice() : SharedWrapBase(nullptr) {

    }

    QUrl getUrl()const { return wrapped()->getUrl(); }
    SharedReadWriteLock getLock()const { return wrapped()->getLock(); }
    bool isFixedSize()const { return wrapped()->isFixedSize(); }
    bool isReadOnly()const { return wrapped()->isReadOnly(); }
    qulonglong getLength()const { return wrapped()->getLength(); }
    const LoadOptions &getLoadOptions()const { return wrapped()->getLoadOptions(); }

    QByteArray read(qulonglong position, qulonglong length)const { return wrapped()->read(position, length); }
    QByteArray readAll()const { return wrapped()->readAll(); }
    qulonglong write(qulonglong position, const QByteArray &data) { return wrapped()->write(position, data); }
    void resize(qulonglong new_size) { wrapped()->resize(new_size); }

    qulonglong getCacheSize()const { return wrapped()->getCacheSize(); }
    void setCacheSize(qulonglong new_cache_size) { wrapped()->setCacheSize(new_cache_size); }
};


class SharedDeviceSpan : public SharedAbstractSpan {
public:
    SharedDeviceSpan(const std::shared_ptr<DeviceSpan> &wrapped) : SharedAbstractSpan(wrapped) {

    }

    SharedDeviceSpan(const SharedAbstractDevice &device, qulonglong device_offset, qulonglong length)
        : SharedAbstractSpan(std::make_shared<DeviceSpan>(device.wrapped(), device_offset, length)) {

    }
};


class SharedFileDevice : public SharedAbstractDevice {
public:
    SharedFileDevice(const std::shared_ptr<FileDevice> &wrapped) : SharedAbstractDevice(wrapped) {

    }
};


class SharedBufferDevice : public SharedAbstractDevice {
public:
    SharedBufferDevice(const std::shared_ptr<BufferDevice> &wrapped) : SharedAbstractDevice(wrapped) {

    }
};


typedef QList<SharedAbstractSpan> SharedSpanList;


class SharedSpanChain : public SharedWrapBase<SpanChain> {
public:
    SharedSpanChain(const std::shared_ptr<SpanChain> &wrapped=std::shared_ptr<SpanChain>()) : SharedWrapBase(wrapped) {

    }

    qulonglong getLength()const { return wrapped()->getLength(); }
    SharedReadWriteLock getLock()const { return wrapped()->getLock(); }

    SharedSpanList getSpans()const { return _toSharedList(wrapped()->getSpans()); }
    void setSpans(const SharedSpanList &spans) { wrapped()->setSpans(_toList(spans)); }
    void clear() { wrapped()->clear(); }

    QByteArray read(qulonglong offset, qulonglong length)const { return wrapped()->read(offset, length); }
    QByteArray readAll()const { return wrapped()->readAll(); }
    SharedSpanList spansInRange(qulonglong offset, qulonglong length, qulonglong *left_offset=0,
                          qulonglong *right_offset=0)const {
        return _toSharedList(wrapped()->spansInRange(offset, length, left_offset, right_offset));
    }
    SharedAbstractSpan spanAtOffset(qulonglong offset, qulonglong *span_offset=0)const {
        return wrapped()->spanAtOffset(offset, span_offset);
    }
    SharedSpanList takeSpans(qulonglong offset, qulonglong length) {
        return _toSharedList(wrapped()->takeSpans(offset, length));
    }
    void splitSpans(qulonglong offset) {
        wrapped()->splitSpans(offset);
    }

    void insertSpan(qulonglong offset, SharedAbstractSpan &span) {
        wrapped()->insertSpan(offset, span.wrapped());
    }
    void insertChain(qulonglong offset, SharedSpanChain &chain) {
        wrapped()->insertChain(offset, chain.wrapped());
    }
    void remove(qulonglong offset, qulonglong length) {
        wrapped()->remove(offset, length);
    }

    SharedSpanChain takeChain(qulonglong offset, qulonglong length)const {
        return wrapped()->exportRange(offset, length);
    }

    SharedSpanChain exportRange(qulonglong offset, qulonglong length, int ram_limit=-1)const {
        return wrapped()->exportRange(offset, length, ram_limit);
    }

private:
    static SharedSpanList _toSharedList(const SpanList &list) {
        SharedSpanList result;
        for (auto span : list) {
            result.append(SharedAbstractSpan(span));
        }
        return result;
    }

    static SpanList _toList(const SharedSpanList &list) {
        SpanList result;
        for (auto span : list) {
            result.append(span.wrapped());
        }
        return result;
    }
};


class SharedDocument : public QObject, public SharedWrapBase<Document> {
    Q_OBJECT
public:
    SharedDocument(const std::shared_ptr<Document> &wrapped) : SharedWrapBase(wrapped) {
        connectSignals();
    }

    SharedDocument(const SharedAbstractDevice &device) : SharedWrapBase(std::make_shared<Document>(device.wrapped())) {
        connectSignals();
    }

    SharedDocument() : SharedWrapBase(std::make_shared<Document>()) {
        connectSignals();
    }

    SharedAbstractDevice getDevice()const { return wrapped()->getDevice(); }
    SharedReadWriteLock getLock()const { return wrapped()->getLock(); }
    QUrl getUrl()const { return wrapped()->getUrl(); }
    qulonglong getLength()const { return wrapped()->getLength(); }
    bool isFixedSize()const { return wrapped()->isFixedSize(); }
    void setFixedSize(bool f) { wrapped()->setFixedSize(f); }
    bool isReadOnly()const { return wrapped()->isReadOnly(); }
    void setReadOnly(bool r) { wrapped()->setReadOnly(r); }

    QByteArray read(qulonglong position, qulonglong length)const { return wrapped()->read(position, length); }
    QByteArray readAll()const { return wrapped()->readAll(); }

    void insertSpan(qulonglong position, const SharedAbstractSpan &span, char fill_byte=0) {
        wrapped()->insertSpan(position, span.wrapped(), fill_byte);
    }
    void insertChain(qulonglong position, const SharedSpanChain &chain, char fill_byte=0) {
        wrapped()->insertChain(position, chain.wrapped(), fill_byte);
    }
    void appendSpan(const SharedAbstractSpan &span) { wrapped()->appendSpan(span.wrapped()); }
    void appendChain(const SharedSpanChain &chain) { wrapped()->appendChain(chain.wrapped()); }
    void writeSpan(qulonglong position, const SharedAbstractSpan &span, char fill_byte=0) {
        wrapped()->writeSpan(position, span.wrapped(), fill_byte);
    }
    void writeChain(qulonglong position, const SharedSpanChain &chain, char fill_byte=0) {
        wrapped()->writeChain(position, chain.wrapped(), fill_byte);
    }
    void remove(qulonglong position, qulonglong length) { wrapped()->remove(position, length); }
    void clear() { wrapped()->clear(); }

    bool isModified()const { return wrapped()->isModified(); }
    bool isRangeModified(qulonglong position, qulonglong length)const { return wrapped()->isRangeModified(position, length); }

    void undo() { return wrapped()->undo(); }
    void redo(int branch_id=-1) { return wrapped()->redo(branch_id); }
    void beginComplexAction(const QString &title=QString()) { wrapped()->beginComplexAction(title); }
    void endComplexAction() { wrapped()->endComplexAction(); }
    bool canUndo()const { return wrapped()->canUndo(); }
    bool canRedo()const { return wrapped()->canRedo(); }
    QList<int> getAlternativeBranchesIds()const { return wrapped()->getAlternativeBranchesIds(); }

    void save(const SharedAbstractDevice *write_device=nullptr, bool switch_devices=false) {
        wrapped()->save(write_device ? write_device->wrapped() : std::shared_ptr<AbstractDevice>(), switch_devices);
    }

    SharedSpanChain exportRange(qulonglong position, qulonglong length, int ram_limit=-1)const {
        return wrapped()->exportRange(position, length, ram_limit);
    }

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

private:
    void connectSignals() {
    #define DO_CONNECT(S) connect(w, SIGNAL(S), this, SIGNAL(S));

        Document *w = _wrapped.get();
        if (!w) {
            return;
        }

        DO_CONNECT(dataChanged(qulonglong, qulonglong));
        DO_CONNECT(bytesInserted(qulonglong, qulonglong));
        DO_CONNECT(bytesRemoved(qulonglong, qulonglong));
        DO_CONNECT(resized(qulonglong));
        DO_CONNECT(canUndoChanged(bool));
        DO_CONNECT(canRedoChanged(bool));
        DO_CONNECT(isModifiedChanged(bool));
        DO_CONNECT(urlChanged(const QUrl &));
        DO_CONNECT(readOnlyChanged(bool));
        DO_CONNECT(fixedSizeChanged(bool));

    #undef DO_CONNECT
    }
};


class SharedBinaryFinder : public SharedWrapBase<BinaryFinder> {
public:
    SharedBinaryFinder(const std::shared_ptr<BinaryFinder> &wrapped) : SharedWrapBase(wrapped) {

    }

    SharedBinaryFinder(const SharedDocument &document, const QByteArray &findWhat) :
        SharedWrapBase(std::make_shared<BinaryFinder>(document.wrapped(), findWhat)) {

    }

    qulonglong findNext(qulonglong from_position, qulonglong limit, bool *ok) {
        return wrapped()->findNext(from_position, limit, ok);
    }

    qulonglong findPrevious(qulonglong from_position, qulonglong limit, bool *ok) {
        return wrapped()->findPrevious(from_position, limit, ok);
    }
};


inline SharedAbstractDevice sharedDeviceFromUrl(const QUrl &url, const LoadOptions &options) {
    return deviceFromUrl(url, options);
}

inline SharedFileDevice sharedDeviceFromFile(const QString &file, const FileLoadOptions &options=FileLoadOptions()) {
    return deviceFromFile(file, options);
}

inline SharedBufferDevice sharedDeviceFromData(const QByteArray &data, const BufferLoadOptions &options=BufferLoadOptions()) {
    return deviceFromData(data, options);
}

namespace Clipboard {

inline void sharedSetData(const SharedDocument &document, qulonglong position, qulonglong length) {
    setData(document.wrapped(), position, length);
}

inline SharedSpanChain sharedGetData() {
    return getData();
}

inline bool sharedHasMicrohexData() {
    return hasMicrohexData();
}

}

#endif
