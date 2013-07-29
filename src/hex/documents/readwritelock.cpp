#include "readwritelock.h"
#include <chrono>

ReadWriteLock::ReadWriteLock() : _writeLockCount(0) {

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
    std::thread::id current_thread_id = std::this_thread::get_id();

    std::lock_guard<std::mutex> lock(_mutex);
    if (!_readers.contains(current_thread_id)) {
        throw std::runtime_error("unlocking ReadWriteLock that was not locked for read");
    }

    _readers[current_thread_id] -= 1;
    if (!_readers[current_thread_id]) {
        _readers.remove(current_thread_id);

        // check if we can let writer to begin. This is possible only if there are no other readers, or
        // all reader threads are waiting for write lock too, and there should be no other active writer.
        if (_activeWriter == std::thread::id() && !_hasParallelReaders()) {
            _canWriteCondition.notify_one();
        }
    }
}

void ReadWriteLock::unlockWrite() {
    std::thread::id current_thread_id = std::this_thread::get_id();

    std::lock_guard<std::mutex> lock_guard(_mutex);

    if (_activeWriter != current_thread_id || _writeLockCount == 0) {
        throw std::runtime_error("unlocking ReadWriteLock that was not locked for write by this thread");
    }

    _writeLockCount -= 1;
    if (_writeLockCount == 0) {
        _activeWriter = std::thread::id();
        if (_pendingWriters.isEmpty()) {
            _canReadCondition.notify_all();
        } else {
            _canWriteCondition.notify_one();
        }
    }
}

bool ReadWriteLock::_acquireRead(bool blocking, int timeout) {
    std::thread::id current_thread_id = std::this_thread::get_id();

    std::lock_guard<std::mutex> lock_guard(_mutex);

    bool ok = false; // is read lock acquired
    if (_canReadNow()) {
        ok = true;
    } else if (blocking) {
        std::unique_lock<std::mutex> lock(_mutex, std::adopt_lock);

        if (timeout >= 0) {
            ok = _canReadCondition.wait_for(lock, std::chrono::milliseconds(timeout),
                                        [this]()->bool { return this->_canReadNow(); });
        } else {
            _canReadCondition.wait(lock, [this]()->bool { return this->_canReadNow(); });
            ok = _canReadNow();
        }
    }

    if (ok) {
        if (_readers.contains(current_thread_id)) {
            _readers[current_thread_id] += 1;
        } else {
            _readers[current_thread_id] = 1;
        }
    }

    return ok;
}

bool ReadWriteLock::_acquireWrite(bool blocking, int timeout) {
    std::thread::id current_thread_id = std::this_thread::get_id();

    std::lock_guard<std::mutex> lock_guard(_mutex);

    bool ok = false; // is write lock acquired
    if (_canWriteNow()) {
        ok = true;
    } else if (blocking) {
        _pendingWriters.append(current_thread_id);
        std::unique_lock<std::mutex> lock(_mutex, std::adopt_lock);

        if (timeout >= 0) {
            ok = _canWriteCondition.wait_for(lock, std::chrono::milliseconds(timeout),
                                         [this](){ return this->_canWriteNow(); });
        } else {
            _canWriteCondition.wait(lock, [this](){ return this->_canWriteNow(); });
            ok = _canWriteNow();
        }
        _pendingWriters.removeOne(current_thread_id);
    }

    if (ok) {
        _activeWriter = current_thread_id;
        _writeLockCount += 1;
    }

    return ok;
}

bool ReadWriteLock::_canReadNow() {
    std::thread::id current_thread_id = std::this_thread::get_id();
    return _readers.contains(current_thread_id) || _activeWriter == current_thread_id ||
            (_activeWriter == std::thread::id() && _pendingWriters.isEmpty());
}

bool ReadWriteLock::_hasParallelReaders() {
    // returns true if there are active readers (not waiting for write lock) except current one
    std::thread::id current_thread_id = std::this_thread::get_id();
    for (auto thread_id : _readers.keys()) {
        if (thread_id != current_thread_id && !_pendingWriters.contains(thread_id)) {
            return true;
        }
    }
    return false;
}

bool ReadWriteLock::_canWriteNow() {
    std::thread::id current_thread_id = std::this_thread::get_id();
    return _activeWriter == current_thread_id ||
            (_activeWriter == std::thread::id() && !_hasParallelReaders()) ||
            (_readers.contains(current_thread_id) && !_hasParallelReaders());
}
