#ifndef TESTS_H
#define TESTS_H

#include <QObject>
#include <QTemporaryFile>
#include <QtTest/QTest>
#include <QtTest/QSignalSpy>
#include <QDebug>
#include <memory>
#include "devices.h"
#include "spans.h"
#include "chain.h"
#include "document.h"

class DeviceTest : public QObject {
    Q_OBJECT
private slots:
    void testBufferDevice() {
        QByteArray data("Hello, World!");
        QByteArray control_data = data;

        BufferDevice *device = new BufferDevice(&data);
        testDevice(device, control_data);

        QCOMPARE(device->url(), QUrl("data://"));
    }

    void testFileDevice() {
        QByteArray file_data;

        QTemporaryFile temp_file;
        temp_file.open();
        temp_file.write(file_data);
        temp_file.close();

        FileDevice *device = new FileDevice(temp_file.fileName());
        testDevice(device, file_data);

        QCOMPARE(device->url(), QUrl::fromLocalFile(temp_file.fileName()));
    }

private:
    void testDevice(AbstractDevice *device, const QByteArray &realData) {
        QCOMPARE(device->length(), qulonglong(realData.length()));
        QCOMPARE(device->read(0, device->length()), realData);
        QCOMPARE(device->read(0, device->length() + 1), realData);
        QCOMPARE(device->read(device->length() + 1000, 2), QByteArray());
        QCOMPARE(device->read(0, 1), realData.mid(0, 1));
        QCOMPARE(device->read(2, 4), realData.mid(2, 4));

        device->resize(0);
        QCOMPARE(device->length(), qulonglong(0));
        QCOMPARE(device->read(0, device->length()), QByteArray());

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
        testSpan(new DataSpan(data), data);
    }

    void testFillSpan() {
        testSpan(new FillSpan('x', 100), QByteArray(100, 'x'));
    }

    void testDeviceSpan() {
        QByteArray data("Lorem ipsum dolor sit amet, consectetur adipisicing elit, sed do eiusmod tempor "
                        "incididunt ut labore et dolore magna aliqua. Ut enim ad minim veniam, quis nostrud "
                        "exercitation ullamco laboris nisi ut aliquip ex ea commodo consequat. Duis aute "
                        "irure dolor in reprehenderit in voluptate velit esse cillum dolore eu fugiat nulla "
                        "pariatur. Excepteur sint occaecat cupidatat non proident, sunt in culpa qui "
                        "officia deserunt mollit anim id est laborum.");
        AbstractDevice *device = new BufferDevice(&data);
        auto span = device->createSpan(20, 100);
        testSpan(span, data.mid(20, 100));
        QCOMPARE(span->deviceOffset(), qulonglong(20));
        QCOMPARE(span->device(), device);
    }

private:
    void testSpan(AbstractSpan *span, const QByteArray &real_data, bool cloned=false) {
        QCOMPARE(span->length(), qulonglong(real_data.length()));
        QCOMPARE(span->read(0, span->length()), real_data);
        QCOMPARE(span->read(2, 5), real_data.mid(2, 5));

        try {
            QCOMPARE(span->read(2, span->length() + 2000), real_data.mid(2));
            QFAIL("exception was not thrown");
        } catch (const OutOfBoundsError &) {

        }

        try {
            span->read(2, span->length() + 200);
            QFAIL("exception was not thrown");
        } catch (const OutOfBoundsError &) {

        }

        try {
            span->read(span->length(), 1);
            QFAIL("exception was not thrown");
        } catch (const OutOfBoundsError &) {

        }

        if (!cloned) {
            auto cloned_one = span->clone();
            testSpan(cloned_one, real_data, true);
            delete cloned_one;

            auto splitted = span->split(10);
            testSpan(splitted.first, real_data.mid(0, 10), true);
            testSpan(splitted.second, real_data.mid(10), true);
            delete splitted.first;
            delete splitted.second;
        }

        try {
            span->split(0);
            QFAIL("exception was not thrown");
        } catch (const OutOfBoundsError &) {

        }

        try {
            span->split(span->length());
            QFAIL("exception was not thrown");
        } catch (const OutOfBoundsError &) {

        }
    }
};


class ChainTest : public QObject {
    Q_OBJECT
private slots:
    void test() {
        SpanChain *chain1 = new SpanChain();
        QCOMPARE(chain1->readAll(), QByteArray());
        QCOMPARE(chain1->length(), qulonglong(0));

        auto chain2 = SpanChain::fromSpans(SpanList()
                    << new DataSpan("Lorem ipsum")
                    << new DataSpan(" dolor sit amet")
        );

        QCOMPARE(chain2->spans().length(), 2);
        qulonglong left, right;
        QCOMPARE(chain2->spansInRange(3, 20, &left, &right), chain2->spans());
        QCOMPARE(left, qulonglong(3));
        QCOMPARE(right, qulonglong(11));
        QCOMPARE(chain2->findSpanIndex(0, &left), 0);
        QCOMPARE(left, qulonglong(0));
        QCOMPARE(chain2->findSpanIndex(chain2->length(), &left), -1);
        QCOMPARE(chain2->findSpanIndex(chain2->length() - 1, &left), 1);
        QCOMPARE(left, chain2->spans()[1]->length() - 1);

        testChain(chain2, QByteArray("Lorem ipsum dolor sit amet"));
    }

private:
    void testChain(SpanChain *chain, const QByteArray &real_data) {
        QCOMPARE(chain->length(), qulonglong(real_data.length()));

        QCOMPARE(chain->readAll(), real_data);
        QCOMPARE(chain->read(2, 4), real_data.mid(2, 4));
        QCOMPARE(chain->read(chain->length(), 1), QByteArray());
        QCOMPARE(chain->read(chain->length() + 200, 200), QByteArray());

        chain->remove(2, 4);
        QCOMPARE(chain->readAll(), real_data.mid(0, 2) + real_data.mid(6));

        chain->insertSpan(2, new DataSpan(real_data.mid(2, 4)));
        QCOMPARE(chain->readAll(), real_data);

        auto chain_part = SpanChain::fromSpans(chain->takeSpans(2, 8));
        QCOMPARE(chain_part->length(), qulonglong(8));
        QCOMPARE(chain_part->readAll(), real_data.mid(2, 8));

        auto part2 = SpanChain::fromSpans(chain->takeSpans(0, chain->length()));
        QCOMPARE(part2->length(), qulonglong(real_data.length()));
        QCOMPARE(part2->readAll(), real_data);
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
        AbstractDevice *device = new BufferDevice(&data);
        auto document = new Document(device);
        testDocument(document, data);

        Document *doc = new Document();
        QCOMPARE(doc->length(), qulonglong(0));
        doc->insertSpan(10, new DataSpan("Hi!"));
        QCOMPARE(doc->readAll(), QByteArray(10, 0) + QByteArray("Hi!"));
    }

private:
    void testDocument(Document *document, const QByteArray &real_data) {
        QCOMPARE(document->length(), qulonglong(real_data.length()));
        QCOMPARE(document->readAll(), real_data);
        QVERIFY(!document->readOnly());
        QVERIFY(!document->fixedSize());

        QSignalSpy dataChangedSpy(document, SIGNAL(dataChanged(qulonglong,qulonglong))),
                resizedSpy(document, SIGNAL(resized(qulonglong))),
                bytesInsertedSpy(document, SIGNAL(bytesInserted(qulonglong,qulonglong))),
                bytesRemovedSpy(document, SIGNAL(bytesRemoved(qulonglong,qulonglong)));

        QVERIFY(!document->canUndo());
        QVERIFY(!document->canRedo());
        QVERIFY(!document->isModified());

        document->insertSpan(3, new FillSpan(0, 10));
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

#endif // TESTS_H
