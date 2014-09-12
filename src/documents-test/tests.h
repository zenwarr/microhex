#ifndef TESTS_H
#define TESTS_H

#include <QObject>
#include <QTemporaryFile>
#include <QDir>
#include <QUuid>
#include <QtTest/QTest>
#include <QtTest/QSignalSpy>
#include <QDebug>
#include <memory>
#include "devices.h"
#include "spans.h"
#include "chain.h"
#include "document.h"
#include "matcher.h"
#include "clipboard.h"
#include <QApplication>
#include <QClipboard>

class DeviceTest : public QObject {
    Q_OBJECT
private slots:
    void testBufferDevice() {
        QByteArray data("Hello, World!");
        QByteArray control_data = data;

        auto device = deviceFromData(data);
        testDevice(device, control_data);

        QCOMPARE(device->getUrl(), QUrl("microdata://"));
    }

    void testFileDevice() {
        QByteArray file_data;

        QTemporaryFile temp_file;
        temp_file.open();
        temp_file.write(file_data);

        auto device = deviceFromFile(temp_file.fileName());
        testDevice(device, file_data);

        QCOMPARE(device->getUrl(), QUrl::fromLocalFile(temp_file.fileName()));

        try {
            QString filename = "this-file-does-not-exist" + QTime::currentTime().toString();
            auto device = deviceFromFile(filename);
            QFAIL("Exception was not thrown");
        } catch (const DeviceError &err) {

        }
    }

    void test() {
        // we cannot open two devices for same underlying device that refers to same data and one of them is not read-only
        QTemporaryFile file;
        file.open();
        file.write(QByteArray(1000, 0));

        FileLoadOptions options;
        options.rangeLoad = true;
        options.rangeStart = 10;
        options.rangeLength = 100;
        auto f1 = deviceFromFile(file.fileName(), options);
        QVERIFY(f1.get());

        options.rangeStart = 15;
        try {
            deviceFromFile(file.fileName(), options);
            QFAIL("Exception was not thrown");
        } catch (const DeviceError &error) {

        }

        try {
            options.readOnly = true;
            deviceFromFile(file.fileName(), options);
            QFAIL("Exception was not thrown");
        } catch (const DeviceError &error) {

        }

        options.readOnly = false;
        options.rangeStart = 300;
        options.rangeLength = 10;
        QVERIFY(deviceFromFile(file.fileName(), options).get());

        options.readOnly = true;
        options.rangeStart = 500;
        options.rangeLength = 100;
        QVERIFY(deviceFromFile(file.fileName(), options).get());

        options.rangeStart = 520;
        QVERIFY(deviceFromFile(file.fileName(), options).get());
    }

    void testCustomCacheSize() {
        QTemporaryFile file;
        file.open();
        file.write("Lorem ipsum dolor sit amet");

        FileLoadOptions options;
        options.memoryLoad = true;
        auto dev = deviceFromFile(file.fileName(), options);
    }

private:
    void testDevice(const std::shared_ptr<AbstractDevice> &device, const QByteArray &realData) {
        QCOMPARE(device->getLength(), qulonglong(realData.length()));
        QCOMPARE(device->read(0, device->getLength()), realData);
        QCOMPARE(device->read(0, device->getLength() + 1), realData);
        QCOMPARE(device->read(device->getLength() + 1000, 2), QByteArray());
        QCOMPARE(device->read(0, 1), realData.mid(0, 1));
        QCOMPARE(device->read(2, 4), realData.mid(2, 4));

        device->resize(0);
        QCOMPARE(device->getLength(), qulonglong(0));
        QCOMPARE(device->read(0, device->getLength()), QByteArray());

        device->write(0, "Lorem ipsum");
        QCOMPARE(device->readAll(), QByteArray("Lorem ipsum"));
        device->write(1, "Lorem");
        QCOMPARE(device->readAll(), QByteArray("LLoremipsum"));
    }
};


class SpansTest : public QObject {
    Q_OBJECT
private slots:
    void testDataSpan() {
        QByteArray data("Lorem ipsum dolor sit amet, consectetur adipisicing elit, sed do eiusmod tempor "
                        "incididunt ut labore et dolore magna aliqua. Ut enim ad minim veniam, quis nostrud "
                        "exercitation ullamco laboris nisi ut aliquip ex ea commodo consequat. Duis aute "
                        "irure dolor in reprehenderit in voluptate velit esse cillum dolore eu fugiat nulla "
                        "pariatur. Excepteur sint occaecat cupidatat non proident, sunt in culpa qui "
                        "officia deserunt mollit anim id est laborum.");
        testSpan(std::make_shared<DataSpan>(data), data);
    }

    void testFillSpan() {
        testSpan(std::make_shared<FillSpan>(100, 'x'), QByteArray(100, 'x'));
    }

    void testDeviceSpan() {
        QByteArray data("Lorem ipsum dolor sit amet, consectetur adipisicing elit, sed do eiusmod tempor "
                        "incididunt ut labore et dolore magna aliqua. Ut enim ad minim veniam, quis nostrud "
                        "exercitation ullamco laboris nisi ut aliquip ex ea commodo consequat. Duis aute "
                        "irure dolor in reprehenderit in voluptate velit esse cillum dolore eu fugiat nulla "
                        "pariatur. Excepteur sint occaecat cupidatat non proident, sunt in culpa qui "
                        "officia deserunt mollit anim id est laborum.");
        auto device = deviceFromData(data);
        testSpan(device->createSpan(20, 100), data.mid(20, 100));
    }

private:
    void testSpan(const std::shared_ptr<AbstractSpan> &span, const QByteArray &real_data, bool cloned=false) {
        QCOMPARE(span->getLength(), qulonglong(real_data.length()));
        QCOMPARE(span->read(0, span->getLength()), real_data);
        QCOMPARE(span->read(2, 5), real_data.mid(2, 5));

        try {
            QCOMPARE(span->read(2, span->getLength() + 2000), real_data.mid(2));
            QFAIL("exception was not thrown");
        } catch (const OutOfBoundsError &) {

        }

        try {
            span->read(2, span->getLength() + 200);
            QFAIL("exception was not thrown");
        } catch (const OutOfBoundsError &) {

        }

        try {
            span->read(span->getLength(), 1);
            QFAIL("exception was not thrown");
        } catch (const OutOfBoundsError &) {

        }

        if (!cloned) {
            auto splitted = span->split(10);
            testSpan(splitted.first, real_data.mid(0, 10), true);
            testSpan(splitted.second, real_data.mid(10), true);
        }

        try {
            span->split(0);
            QFAIL("exception was not thrown");
        } catch (const OutOfBoundsError &) {

        }

        try {
            span->split(span->getLength());
            QFAIL("exception was not thrown");
        } catch (const OutOfBoundsError &) {

        }
    }
};


class ChainTest : public QObject {
    Q_OBJECT
private slots:
    void test() {
        auto chain1 = std::make_shared<SpanChain>();
        QCOMPARE(chain1->readAll(), QByteArray());
        QCOMPARE(chain1->getLength(), qulonglong(0));

        auto chain2 = SpanChain::fromSpans(SpanList()
                                           << std::make_shared<DataSpan>("Lorem ipsum")
                                           << std::make_shared<DataSpan>(" dolor sit amet"));

        QCOMPARE(chain2->getSpans().length(), 2);
        qulonglong left, right;
        QCOMPARE(chain2->spansInRange(3, 20, &left, &right), chain2->getSpans());
        QCOMPARE(left, qulonglong(3));
        QCOMPARE(right, qulonglong(11));

        testChain(chain2, QByteArray("Lorem ipsum dolor sit amet"));
    }

    void testExport() {
        QTemporaryFile file;
        file.open();
        file.write(QByteArray(1024 * 1024 * 16, '\xff'));

        auto dev = deviceFromFile(file.fileName());
        auto chain = SpanChain::fromSpans(SpanList() << std::make_shared<DeviceSpan>(dev, 0, dev->getLength()));

        auto exported = chain->exportRange(0, 500, -1);
        QCOMPARE(exported->readAll(), QByteArray(500, '\xff'));
        QVERIFY(std::dynamic_pointer_cast<DataSpan>(exported->getSpans()[0]).get());

        auto exported2 = chain->exportRange(0, 500, 0);
        QVERIFY(std::dynamic_pointer_cast<DeviceSpan>(exported2->getSpans()[0]).get());

        auto exported3 = chain->exportRange(0, chain->getLength());
        QCOMPARE(exported3->readAll(), chain->readAll());
    }

private:
    void testChain(const std::shared_ptr<SpanChain> &chain, const QByteArray &real_data) {
        QCOMPARE(chain->getLength(), qulonglong(real_data.length()));

        QCOMPARE(chain->readAll(), real_data);
        QCOMPARE(chain->read(2, 4), real_data.mid(2, 4));
        QCOMPARE(chain->read(chain->getLength(), 1), QByteArray());
        QCOMPARE(chain->read(chain->getLength() + 200, 200), QByteArray());

        chain->remove(2, 4);
        QCOMPARE(chain->readAll(), real_data.mid(0, 2) + real_data.mid(6));

        chain->insertSpan(2, std::make_shared<DataSpan>(real_data.mid(2, 4)));
        QCOMPARE(chain->readAll(), real_data);

        auto chain_part = SpanChain::fromSpans(chain->takeSpans(2, 8));
        QCOMPARE(chain_part->getLength(), qulonglong(8));
        QCOMPARE(chain_part->readAll(), real_data.mid(2, 8));

        auto part2 = SpanChain::fromSpans(chain->takeSpans(0, chain->getLength()));
        QCOMPARE(part2->getLength(), qulonglong(real_data.length()));
        QCOMPARE(part2->readAll(), real_data);

        chain->clear();
        QCOMPARE(chain->getLength(), qulonglong(0));
        QCOMPARE(chain->readAll(), QByteArray());
    }
};


class DocumentTest : public QObject {
    Q_OBJECT
private slots:
    void test() {
        QByteArray data("Lorem ipsum dolor sit amet, consectetur adipisicing elit, sed do eiusmod tempor "
                        "incididunt ut labore et dolore magna aliqua. Ut enim ad minim veniam, quis nostrud "
                        "exercitation ullamco laboris nisi ut aliquip ex ea commodo consequat. Duis aute "
                        "irure dolor in reprehenderit in voluptate velit esse cillum dolore eu fugiat nulla "
                        "pariatur. Excepteur sint occaecat cupidatat non proident, sunt in culpa qui "
                        "officia deserunt mollit anim id est laborum.");
        auto device = deviceFromData(data);
        auto document = std::make_shared<Document>(device);
        testDocument(document, data);
    }

    void test2() {
        auto doc = std::make_shared<Document>();
        QCOMPARE(doc->getLength(), qulonglong(0));
        doc->insertSpan(10, std::make_shared<DataSpan>("Hi!"));
        QCOMPARE(doc->readAll(), QByteArray(10, 0) + QByteArray("Hi!"));
    }

    void test3() {
        auto doc3 = std::make_shared<Document>();
        doc3->appendSpan(std::make_shared<DataSpan>("lorem ipsum"));
        QCOMPARE(doc3->getLength(), qulonglong(11));
        doc3->writeSpan(0, std::make_shared<FillSpan>(doc3->getLength(), 0));
        QCOMPARE(doc3->getLength(), qulonglong(11));
        QCOMPARE(doc3->readAll(), QByteArray(11, 0));
    }

    void test4() {
        QByteArray data("Lorem ipsum dolor sit amet, consectetur adipisicing elit, sed do eiusmod tempor "
                        "incididunt ut labore et dolore magna aliqua. Ut enim ad minim veniam, quis nostrud "
                        "exercitation ullamco laboris nisi ut aliquip ex ea commodo consequat. Duis aute "
                        "irure dolor in reprehenderit in voluptate velit esse cillum dolore eu fugiat nulla "
                        "pariatur. Excepteur sint occaecat cupidatat non proident, sunt in culpa qui "
                        "officia deserunt mollit anim id est laborum.");

        BufferLoadOptions load_options;
        load_options.rangeLoad = true;
        load_options.rangeStart = 10;
        load_options.rangeLength = 100;
        auto rangeDevice = deviceFromData(data, load_options);
        auto rangeDocument = std::make_shared<Document>(rangeDevice);

        rangeDocument->writeSpan(0, std::make_shared<FillSpan>(rangeDocument->getLength(), 0));
        QCOMPARE(rangeDocument->getLength(), qulonglong(100));
        rangeDocument->save();
        data = rangeDevice->getBufferLoadOptions().data;
        QCOMPARE(data.mid(10, 100), QByteArray(100, 0));
        QCOMPARE(data.mid(0, 10), QByteArray("Lorem ipsu"));
        QCOMPARE(data.mid(110), QByteArray(" magna aliqua. Ut enim ad minim veniam, quis nostrud exercitation ullamco laboris nisi "
                                           "ut aliquip ex ea commodo consequat. Duis aute irure dolor in reprehenderit in voluptate "
                                           "velit esse cillum dolore eu fugiat nulla pariatur. Excepteur sint occaecat cupidatat non "
                                           "proident, sunt in culpa qui officia deserunt mollit anim id est laborum."));
    }

    void testSave() {
        QByteArray data(1024 * 1024 * 16, '\xff');

        QTemporaryFile file;
        file.open();
        file.write(data);

        auto file_device = deviceFromFile(file.fileName());
        auto document = std::make_shared<Document>(file_device);
        auto test_chain = SpanChain::fromSpans(SpanList()
                             << std::make_shared<DeviceSpan>(file_device, 0, file_device->getLength()));
        document->clear();
        document->save();

        // stored device span should become replaced with DataSpan
        QCOMPARE(test_chain->getLength(), qulonglong(data.length()));
        QCOMPARE(test_chain->readAll(), data);
        QCOMPARE(test_chain->getSpans().length(), 1);
        QVERIFY(std::dynamic_pointer_cast<DeviceSpan>(test_chain->getSpans()[0]).get());
        QVERIFY(std::dynamic_pointer_cast<DataSpan>(
                    std::dynamic_pointer_cast<DeviceSpan>(test_chain->getSpans()[0])->getSpans()[0]).get());

        document->undo();
        QCOMPARE(document->readAll(), data);

        document->save();

        auto test_chain2 = SpanChain::fromSpans(SpanList() <<
                              std::make_shared<DeviceSpan>(file_device, 0, file_device->getLength()));
        document->remove(40, 100);
        document->save();
        QCOMPARE(test_chain2->getLength(), qulonglong(data.length()));
        QCOMPARE(test_chain2->readAll(), data);
        QVERIFY(std::dynamic_pointer_cast<DeviceSpan>(test_chain2->getSpans()[0]).get());
        auto dev_span = std::dynamic_pointer_cast<DeviceSpan>(test_chain2->getSpans()[0]);
        QCOMPARE(dev_span->getSpans().length(), 3);
        QVERIFY(std::dynamic_pointer_cast<PrimitiveDeviceSpan>(dev_span->getSpans()[0]).get());
        QVERIFY(std::dynamic_pointer_cast<DataSpan>(dev_span->getSpans()[1]).get());
        QVERIFY(std::dynamic_pointer_cast<PrimitiveDeviceSpan>(dev_span->getSpans()[2]).get());
    }

    void test5() {
        QByteArray data("Lorem ipsum dolor sit amet, consectetur adipisicing elit, sed do eiusmod tempor "
                        "incididunt ut labore et dolore magna aliqua. Ut enim ad minim veniam, quis nostrud "
                        "exercitation ullamco laboris nisi ut aliquip ex ea commodo consequat. Duis aute "
                        "irure dolor in reprehenderit in voluptate velit esse cillum dolore eu fugiat nulla "
                        "pariatur. Excepteur sint occaecat cupidatat non proident, sunt in culpa qui "
                        "officia deserunt mollit anim id est laborum.");
        auto device = deviceFromData(data);
        auto document = std::make_shared<Document>(device);

        QVERIFY(!document->isModified());
        QVERIFY(!document->isRangeModified(10, 20));

        document->writeSpan(10, std::make_shared<FillSpan>(30, '0'));
        QVERIFY(document->isModified());
        QVERIFY(!document->isRangeModified(0, 4));
        QVERIFY(!document->isRangeModified(0, 10));
        QVERIFY(document->isRangeModified(10, 5));
        QVERIFY(!document->isRangeModified(45, 2));
    }

    void testUndo() {
        QByteArray data("Lorem ipsum dolor sit amet, consectetur adipisicing elit, sed do eiusmod tempor "
                        "incididunt ut labore et dolore magna aliqua. Ut enim ad minim veniam, quis nostrud "
                        "exercitation ullamco laboris nisi ut aliquip ex ea commodo consequat. Duis aute "
                        "irure dolor in reprehenderit in voluptate velit esse cillum dolore eu fugiat nulla "
                        "pariatur. Excepteur sint occaecat cupidatat non proident, sunt in culpa qui "
                        "officia deserunt mollit anim id est laborum.");
        auto device(deviceFromData(data));
        auto document(std::make_shared<Document>(device));

        QSignalSpy canUndoSpy(document.get(), SIGNAL(canUndoChanged(bool)));
        QSignalSpy canRedoSpy(document.get(), SIGNAL(canRedoChanged(bool)));
        QSignalSpy dataChangedSpy(document.get(), SIGNAL(dataChanged(qulonglong, qulonglong)));

        QVERIFY(!document->isModified());
        document->writeSpan(3, std::make_shared<DataSpan>("x"));
        QCOMPARE(document->readAll(), QByteArray("Lorxm ipsum dolor sit amet, consectetur adipisicing elit, sed do eiusmod tempor "
                 "incididunt ut labore et dolore magna aliqua. Ut enim ad minim veniam, quis nostrud "
                 "exercitation ullamco laboris nisi ut aliquip ex ea commodo consequat. Duis aute "
                 "irure dolor in reprehenderit in voluptate velit esse cillum dolore eu fugiat nulla "
                 "pariatur. Excepteur sint occaecat cupidatat non proident, sunt in culpa qui "
                 "officia deserunt mollit anim id est laborum."));

        QVERIFY(document->isModified());
        QVERIFY(document->isRangeModified(3, 1));
        QVERIFY(!document->isRangeModified(2, 1));

        QCOMPARE(canUndoSpy.length(), 1);
        QCOMPARE(canRedoSpy.length(), 0);
        QCOMPARE(dataChangedSpy.length(), 1);
        QCOMPARE(dataChangedSpy.first(), QList<QVariant>() << qulonglong(3) << qulonglong(1));

        canUndoSpy.clear();
        dataChangedSpy.clear();

        document->undo();
        QVERIFY(!document->isModified());

        QCOMPARE(canUndoSpy.length(), 1);
        QCOMPARE(canUndoSpy.first(), QList<QVariant>() << false);
        QCOMPARE(canRedoSpy.length(), 1);
        QCOMPARE(canRedoSpy.first(), QList<QVariant>() << true);
        QCOMPARE(dataChangedSpy.length(), 1);
        QCOMPARE(dataChangedSpy.first(), QList<QVariant>() << qulonglong(3) << qulonglong(1));

        canUndoSpy.clear();
        canRedoSpy.clear();
        dataChangedSpy.clear();

        QCOMPARE(document->readAll(), data);

        document->redo();
        QVERIFY(document->isModified());
        QVERIFY(document->isRangeModified(3, 1));

        QCOMPARE(canUndoSpy.length(), 1);
        QCOMPARE(canUndoSpy.first(), QList<QVariant>() << true);
        QCOMPARE(canRedoSpy.length(), 1);
        QCOMPARE(canRedoSpy.first(), QList<QVariant>() << false);
        QCOMPARE(dataChangedSpy.length(), 1);
        QCOMPARE(dataChangedSpy.first(), QList<QVariant>() << qulonglong(3) << qulonglong(1));

        canUndoSpy.clear();
        canRedoSpy.clear();
        dataChangedSpy.clear();

        QCOMPARE(document->readAll(), QByteArray("Lorxm ipsum dolor sit amet, consectetur adipisicing elit, sed do eiusmod tempor "
                                                 "incididunt ut labore et dolore magna aliqua. Ut enim ad minim veniam, quis nostrud "
                                                 "exercitation ullamco laboris nisi ut aliquip ex ea commodo consequat. Duis aute "
                                                 "irure dolor in reprehenderit in voluptate velit esse cillum dolore eu fugiat nulla "
                                                 "pariatur. Excepteur sint occaecat cupidatat non proident, sunt in culpa qui "
                                                 "officia deserunt mollit anim id est laborum."));

        document->undo();

        dataChangedSpy.clear();

        QVERIFY(!document->isModified());

        document->writeSpan(10, std::make_shared<FillSpan>(20, 0));

        QCOMPARE(dataChangedSpy.length(), 1);
        QCOMPARE(dataChangedSpy.first(), QVariantList() << qulonglong(10) << qulonglong(20));

        document->undo();

        dataChangedSpy.clear();

        document->writeSpan(13, std::make_shared<DataSpan>("hi"));
        QVERIFY(document->isRangeModified(13, 1));
        QVERIFY(!document->isRangeModified(12, 1));
    }

    void test6() {
        auto document(std::make_shared<Document>());
        document->writeSpan(100, std::make_shared<DataSpan>("Hi!"));
        QCOMPARE(document->readAll(), QByteArray(100, 0) + QByteArray("Hi!"));

        document->undo();

        QCOMPARE(document->getLength(), 0ull);
        QCOMPARE(document->readAll(), QByteArray());
    }

    void test7() {
        QByteArray data("Lorem ipsum dolor sit amet, consectetur adipisicing elit, sed do eiusmod tempor "
                        "incididunt ut labore et dolore magna aliqua. Ut enim ad minim veniam, quis nostrud "
                        "exercitation ullamco laboris nisi ut aliquip ex ea commodo consequat. Duis aute "
                        "irure dolor in reprehenderit in voluptate velit esse cillum dolore eu fugiat nulla "
                        "pariatur. Excepteur sint occaecat cupidatat non proident, sunt in culpa qui "
                        "officia deserunt mollit anim id est laborum.");
        auto device(deviceFromData(data));
        auto document(std::make_shared<Document>(device));

        document->writeSpan(4, std::make_shared<DataSpan>("x"));
        document->writeSpan(5, std::make_shared<DataSpan>("x"));

        document->undo();

        QVERIFY(!document->isRangeModified(5, 1));
    }

    void test8() {
        QByteArray data("1234567890");
        auto device(deviceFromData(data));
        auto document(std::make_shared<Document>(device));

        for (int j = 1; j < 10; ++j) {
            document->writeSpan(j, std::make_shared<DataSpan>("x"));
        }

        document->save();

        QCOMPARE(document->readAll(), QByteArray("1xxxxxxxxx"));
    }

    void test9() {
        QByteArray data("1234567890");
        auto device(deviceFromData(data));
        auto document(std::make_shared<Document>(device));

        document->writeSpan(20, std::make_shared<DataSpan>("x"));
        document->undo();

        QCOMPARE(document->readAll(), data);
        QVERIFY(!document->isModified());

        document->redo();
        document->isModified();
        document->undo();
        document->isModified();

        QCOMPARE(document->readAll(), data);
        QVERIFY(!document->isModified());
    }

    void test10() {
        auto dev = deviceFromData("Lorem ipsum");
        auto doc = std::make_shared<Document>(dev);
        doc->writeSpan(0xfffffffffffffffe, std::make_shared<DataSpan>(QByteArray("\x00", 1)));
        QCOMPARE(doc->getLength(), qulonglong(0xffffffffffffffff));
        QCOMPARE(doc->read(0, 11), QByteArray("Lorem ipsum"));
    }

    void test11() {
        auto dev = deviceFromData("Lorem ipsum");
        auto doc = std::make_shared<Document>(dev);
        doc->beginComplexAction();
        doc->clear();
        doc->endComplexAction();
    }

    void test12() {
        auto doc = std::make_shared<Document>();
        doc->writeSpan(qulonglong(0xfffffffffffffffe), std::make_shared<DataSpan>("x"));
        QCOMPARE(doc->getLength(), qulonglong(0xffffffffffffffff));
        QCOMPARE(doc->read(qulonglong(0xfffffffffffffffe), 2), QByteArray("x"));
    }

    void test13() {
        auto dev = deviceFromData("Lorem ipsum");
        auto doc = std::make_shared<Document>(dev);
        doc->remove(2, 2);
        doc->undo();
        doc->appendSpan(std::make_shared<FillSpan>(10, 0));
        QVERIFY(!doc->isRangeModified(2, 1));
    }

    void testOpenZeroSizeDevice() {
        auto dev = deviceFromData("");
        auto doc = std::make_shared<Document>(dev);
        QCOMPARE(doc->getLength(), qulonglong(0));
    }

    void testFrameDocument() {
        auto dev = deviceFromData("Lorem ipsum");
        auto doc = std::make_shared<Document>(dev);
        doc->writeSpan(2, std::make_shared<DataSpan>("fuck"));
        QCOMPARE(doc->readAll(), QByteArray("Lofuckipsum"));
        auto frame_doc = doc->createConstantFrame(2, 6);
        QCOMPARE(frame_doc->readAll(), QByteArray("fuckip"));
        QCOMPARE(frame_doc->getLength(), qulonglong(6));
        QCOMPARE(frame_doc->isReadOnly(), true);
    }

    void testSaveDocumentWithoutDevice() {
        auto doc = std::make_shared<Document>();
        doc->insertSpan(0, std::make_shared<DataSpan>("Hello, World!"));
        QString filename = QDir::temp().absoluteFilePath(QUuid::createUuid().toString() + ".microhex-tmp");
        FileLoadOptions options;
        options.forceNew = true;
        auto save_device = deviceFromFile(filename, options);
        doc->save(save_device, true);
    }

private:
    void testDocument(const std::shared_ptr<Document> &document, const QByteArray &real_data) {
        QCOMPARE(document->getLength(), qulonglong(real_data.length()));
        QCOMPARE(document->readAll(), real_data);
        QVERIFY(!document->isReadOnly());
        QVERIFY(!document->isFixedSize());

        QSignalSpy dataChangedSpy(document.get(), SIGNAL(dataChanged(qulonglong,qulonglong))),
                resizedSpy(document.get(), SIGNAL(resized(qulonglong))),
                bytesInsertedSpy(document.get(), SIGNAL(bytesInserted(qulonglong,qulonglong))),
                bytesRemovedSpy(document.get(), SIGNAL(bytesRemoved(qulonglong,qulonglong)));

        QVERIFY(!document->canUndo());
        QVERIFY(!document->canRedo());
        QVERIFY(!document->isModified());

        document->insertSpan(3, std::make_shared<FillSpan>(10, 0));
        QCOMPARE(document->readAll(), real_data.mid(0, 3) + QByteArray(10, 0) + real_data.mid(3));
        QCOMPARE(dataChangedSpy.size(), 1);
        QCOMPARE(dataChangedSpy.takeFirst(), QVariantList() << qulonglong(3) << qulonglong(real_data.length() - 3 + 10));
        QCOMPARE(resizedSpy.size(), 1);
        QCOMPARE(resizedSpy.takeFirst(), QVariantList() << qulonglong(real_data.length() + 10));
        QCOMPARE(bytesInsertedSpy.size(), 1);
        QCOMPARE(bytesInsertedSpy.takeFirst(), QVariantList() << qulonglong(3) << qulonglong(10));
        QCOMPARE(bytesRemovedSpy.size(), 0);

        QVERIFY(document->canUndo());
        QVERIFY(!document->canRedo());
        QVERIFY(document->isModified());

        document->undo();
        QCOMPARE(document->readAll(), real_data);

        QVERIFY(!document->canUndo());
        QVERIFY(document->canRedo());
        QVERIFY(!document->isModified());

        document->undo();
        QCOMPARE(document->readAll(), real_data);

        QVERIFY(!document->canUndo());
        QVERIFY(document->canRedo());
        QVERIFY(!document->isModified());

        document->redo();
        QCOMPARE(document->readAll(), real_data.mid(0, 3) + QByteArray(10, 0) + real_data.mid(3));

        QVERIFY(document->canUndo());
        QVERIFY(!document->canRedo());
        QVERIFY(document->isModified());

        document->undo();
        QCOMPARE(document->readAll(), real_data);

        document->remove(0, 5);
        QCOMPARE(document->readAll(), real_data.mid(5));

        document->undo();
        QCOMPARE(document->readAll(), real_data);

        document->redo();
        QCOMPARE(document->readAll(), real_data.mid(5));
    }
};


class MatcherTest : public QObject {
    Q_OBJECT
private slots:
    void test() {
        QByteArray data("Lorem ipsum dolor sit amet, consectetur adipisicing elit, sed do eiusmod tempor "
                        "incididunt ut labore et dolore magna aliqua. Ut enim ad minim veniam, quis nostrud "
                        "exercitation ullamco laboris nisi ut aliquip ex ea commodo consequat. Duis aute "
                        "irure dolor in reprehenderit in voluptate velit esse cillum dolore eu fugiat nulla "
                        "pariatur. Excepteur sint occaecat cupidatat non proident, sunt in culpa qui "
                        "officia deserunt mollit anim id est laborum.");
        auto device = deviceFromData(data);
        auto document = std::make_shared<Document>(device);
        auto finder = std::make_shared<BinaryFinder>(document, "l");
        QCOMPARE(finder->findNext(0), qulonglong(14));

        auto finder2 = std::make_shared<BinaryFinder>(document, "ore");
        QCOMPARE(finder2->findPrevious(10ull), 1ull);
    }

    void test2() {
        QByteArray data("0000xxxxxxxxxxx219031");
        auto device = deviceFromData(data);
        auto document = std::make_shared<Document>(device);
        auto finder = std::make_shared<BinaryFinder>(document, "xxxxx");

        QList<qulonglong> results;
        results << 4ull << 5ull << 6ull << 7ull << 8ull << 9ull << 10ull;

        qulonglong cur_position = 0;
        for (auto result : results) {
            QCOMPARE(finder->findNext(cur_position), result);
            cur_position = result + 1;
        }
        bool ok = true;
        QCOMPARE(finder->findNext(cur_position, -1ull, &ok), 0ull);
        QCOMPARE(ok, false);

        cur_position = document->getLength();
        for (int j = results.length() - 1; j >= 0; --j) {
            QCOMPARE(finder->findPrevious(cur_position), results[j]);
            cur_position = results[j] + 4;
        }
        ok = true;
        QCOMPARE(finder->findPrevious(cur_position, -1ull, &ok), 0ull);
        QCOMPARE(ok, false);

        ok = true;
        QCOMPARE(finder->findPrevious(0, -1ull, &ok), 0ull);
        QCOMPARE(ok, false);
    }

    void test3() {
        QByteArray data("abcddeadbeef");
        auto device = deviceFromData(data);
        auto doc = std::make_shared<Document>(device);
        BinaryFinder finder(doc, "d");
        QCOMPARE(finder.findNext(0), 3ull);
        QCOMPARE(finder.findNext(4), 4ull);
        QCOMPARE(finder.findNext(5), 7ull);
        QCOMPARE(finder.findPrevious(doc->getLength()), 7ull);
        QCOMPARE(finder.findPrevious(7ull), 4ull);
        QCOMPARE(finder.findPrevious(4ull), 3ull);
    }
};


class ClipboardTest : public QObject {
    Q_OBJECT
private slots:
    void test() {
        QByteArray data("Lorem ipsum dolor sit amet, consectetur adipisicing elit, sed do eiusmod tempor "
                        "incididunt ut labore et dolore magna aliqua. Ut enim ad minim veniam, quis nostrud "
                        "exercitation ullamco laboris nisi ut aliquip ex ea commodo consequat. Duis aute "
                        "irure dolor in reprehenderit in voluptate velit esse cillum dolore eu fugiat nulla "
                        "pariatur. Excepteur sint occaecat cupidatat non proident, sunt in culpa qui "
                        "officia deserunt mollit anim id est laborum.");
        auto device = deviceFromData(data);
        auto document = std::make_shared<Document>(device);

        Clipboard::setData(document, 0, document->getLength());

        QVERIFY(Clipboard::hasMicrohexData());

        QCOMPARE(Clipboard::getData()->readAll(), data);
    }
};


#endif // TESTS_H
