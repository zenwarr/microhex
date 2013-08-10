#ifndef READWRITELOCK_H
#define READWRITELOCK_H

#include <QList>
#include <QMap>
#include <QMutex>
#include <QWaitCondition>
#include <QThread>
#include <memory>

class ReadWriteLock : public std::enable_shared_from_this<ReadWriteLock> {
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
    Q_DISABLE_COPY(ReadWriteLock)

    std::unique_ptr<QMutex> _mutex;
    QWaitCondition _canReadCondition, _canWriteCondition;
    QThread *_activeWriter;
    QMap<QThread*, int> _readers;
    QList<QThread*> _pendingWriters;
    int _writeLockCount;

    bool _acquireRead(bool blocking, int timeout);
    bool _acquireWrite(bool blocking, int timeout);
    bool _canReadNow();
    bool _canWriteNow();
    bool _hasParallelReaders();
};


class ReadLocker {
public:
    ReadLocker(const std::shared_ptr<ReadWriteLock> &lock) : _lock(lock) {
        _lock->lockForRead();
    }

    ~ReadLocker() {
        _lock->unlockRead();
    }

private:
    std::shared_ptr<ReadWriteLock> _lock;
};


class WriteLocker {
public:
    WriteLocker(const std::shared_ptr<ReadWriteLock> &lock) : _lock(lock) {
        _lock->lockForWrite();
    }

    ~WriteLocker() {
        _lock->unlockWrite();
    }

private:
    std::shared_ptr<ReadWriteLock> _lock;
};

#endif // READWRITELOCK_H
