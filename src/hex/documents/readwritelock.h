#ifndef READWRITELOCK_H
#define READWRITELOCK_H

#include <mutex>
#include <condition_variable>
#include <thread>
#include <QtGlobal>
#include <QList>
#include <QMap>

class ReadWriteLock {
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

    std::mutex _mutex;
    std::condition_variable _canReadCondition, _canWriteCondition;
    std::thread::id _activeWriter;
    int _writeLockCount;
    QMap<std::thread::id, int> _readers;
    QList<std::thread::id> _pendingWriters;

    bool _acquireRead(bool blocking, int timeout);
    bool _acquireWrite(bool blocking, int timeout);
    bool _canReadNow();
    bool _canWriteNow();
    bool _hasParallelReaders();
};

#endif // READWRITELOCK_H
