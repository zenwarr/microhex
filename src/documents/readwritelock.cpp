#include "readwritelock.h"
#include <stdexcept>
#include <QTime>

ReadWriteLock::ReadWriteLock() : _mutex(new QMutex()), _activeWriter(), _writeLockCount() {

}

ReadWriteLock::~ReadWriteLock() {

}

void ReadWriteLock::lockForRead() {
    _acquireRead(true, -1);
}

bool ReadWriteLock::tryLockForRead(int timeout) {
    return _acquireRead(false, timeout);
}

void ReadWriteLock::lockForWrite() {
    _acquireWrite(true, -1);
}

bool ReadWriteLock::tryLockForWrite(int timeout) {
    return _acquireWrite(false, timeout);
}

void ReadWriteLock::unlockRead() {
    QThread *current_thread = QThread::currentThread();
    QMutexLocker locker(_mutex.get());

    if (!_readers.contains(current_thread)) {
        throw std::runtime_error("unlocking ReadWriteLock that was not locked for read");
    }

    _readers[current_thread] -= 1;
    if (!_readers[current_thread]) {
        _readers.remove(current_thread);

        // check if we can let writer to begin. This is possible only if there are no other readers, or
        // all reader threads are waiting for write lock too, and there should be no other active writer.
        if (!_activeWriter && !_hasParallelReaders()) {
            _canWriteCondition.wakeOne();
        }
    }
}

void ReadWriteLock::unlockWrite() {
    QThread *current_thread = QThread::currentThread();
    QMutexLocker locker(_mutex.get());

    if (_activeWriter != current_thread || _writeLockCount == 0) {
        throw std::runtime_error("unlocking ReadWriteLock that was not locked for write by this thread");
    }

    _writeLockCount -= 1;
    if (_writeLockCount == 0) {
        _activeWriter = nullptr;
        if (_pendingWriters.isEmpty()) {
            _canReadCondition.wakeAll();
        } else {
            _canWriteCondition.wakeOne();
        }
    }
}

bool ReadWriteLock::_acquireRead(bool blocking, int timeout) {
    QThread *current_thread = QThread::currentThread();
    QMutexLocker locker(_mutex.get());

    bool ok = false; // is read lock acquired
    if (_canReadNow()) {
        ok = true;
    } else if (blocking) {
        if (timeout == 0) {
            ok = _canReadNow();
        } else {
            QTime counter;
            counter.start();
            while (!(ok = _canReadNow())) {
                if (timeout >= 0 && counter.elapsed() >= timeout) {
                    break;
                }
                _canReadCondition.wait(_mutex.get(), timeout >= 0 ? std::max(0, timeout - counter.elapsed())
                                                            : -1);
            }
        }
    }

    if (ok) {
        if (_readers.contains(current_thread)) {
            _readers[current_thread] += 1;
        } else {
            _readers[current_thread] = 1;
        }
    }

    return ok;
}

bool ReadWriteLock::_acquireWrite(bool blocking, int timeout) {
    QThread *current_thread = QThread::currentThread();
    QMutexLocker locker(_mutex.get());

    bool ok = false; // is write lock acquired
    if (_canWriteNow()) {
        ok = true;
    } else if (blocking) {
        _pendingWriters.append(current_thread);

        if (timeout == 0) {
            ok = _canWriteNow();
        } else {
            QTime counter;
            counter.start();
            while (!(ok = _canWriteNow()) || timeout < 0 || counter.elapsed() < timeout) {
                _canWriteCondition.wait(_mutex.get(), std::max(0, timeout - counter.elapsed()));
            }
        }

        _pendingWriters.removeOne(current_thread);
    }

    if (ok) {
        _activeWriter = current_thread;
        _writeLockCount += 1;
    }

    return ok;
}

bool ReadWriteLock::_canReadNow() {
    QThread *current_thread = QThread::currentThread();
    return _readers.contains(current_thread) || _activeWriter == current_thread ||
            (!_activeWriter && _pendingWriters.isEmpty());
}

bool ReadWriteLock::_hasParallelReaders() {
    // returns true if there are active readers (not waiting for write lock) except current one
    QThread *current_thread = QThread::currentThread();
    for (auto thread_id : _readers.keys()) {
        if (thread_id != current_thread && !_pendingWriters.contains(thread_id)) {
            return true;
        }
    }
    return false;
}

bool ReadWriteLock::_canWriteNow() {
    QThread *current_thread = QThread::currentThread();
    return _activeWriter == current_thread ||
            (!_activeWriter&& !_hasParallelReaders()) ||
            (_readers.contains(current_thread) && !_hasParallelReaders());
}
