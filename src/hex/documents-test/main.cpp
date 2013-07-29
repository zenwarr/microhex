#include <QCoreApplication>
#include <QtTest/QTest>
#include "tests.h"

//ReadWriteLock rwlock;

int main(int argc, char *argv[])
{
    QCoreApplication a(argc, argv);

    DeviceTest test1;
    QTest::qExec(&test1);

    SpansTest test2;
    QTest::qExec(&test2);

    ChainTest test3;
    QTest::qExec(&test3);

    DocumentTest test4;
    QTest::qExec(&test4);

//    rwlock.lockForRead();
//    rwlock.lockForWrite();

//    rwlock.unlockWrite();
//    rwlock.unlockRead();

//    rwlock.lockForWrite();
//    rwlock.lockForRead();

//    rwlock.unlockRead();
//    rwlock.unlockWrite();

//    rwlock.lockForRead();
//    bool locked = false;

//    std::async(std::launch::async, [&] ()mutable {
//        rwlock.lockForRead();
//        locked = true;
//        rwlock.unlockRead();
//    });

//    // now async has finished (as returned std::future destructor waits until async completed)
//    assert(locked);

//    locked = false;

//    // still locked for read by main thread

//    std::future<void> fut = std::async(std::launch::async, [&] ()mutable {
//        rwlock.lockForWrite(); // should be blocked until main thread releases read lock
//        locked = true;
//        rwlock.unlockWrite();
//    });

//    std::this_thread::sleep_for(std::chrono::seconds(1));
//    assert(!locked);
//    rwlock.unlockRead();
//    std::this_thread::sleep_for(std::chrono::seconds(1));
//    assert(locked);

//    rwlock.lockForWrite();
//    locked = false;

//    fut = std::async(std::launch::async, [&] ()mutable {
//        rwlock.lockForRead();
//        rwlock.lockForWrite();
//        locked = true;
//        rwlock.unlockWrite();
//        rwlock.unlockRead();
//    });

//    assert(!locked);
//    std::this_thread::sleep_for(std::chrono::seconds(1));
//    rwlock.unlockWrite();
//    std::this_thread::sleep_for(std::chrono::seconds(1));
//    assert(locked);

//    qDebug() << "ok!";
}
