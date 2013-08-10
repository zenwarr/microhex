#include <QApplication>
#include <QtTest/QTest>
#include "tests.h"

int main(int argc, char *argv[])
{
    QApplication a(argc, argv);

    DeviceTest test1;
    QTest::qExec(&test1);

    SpansTest test2;
    QTest::qExec(&test2);

    ChainTest test3;
    QTest::qExec(&test3);

    DocumentTest test4;
    QTest::qExec(&test4);

    MatcherTest test5;
    QTest::qExec(&test5);

    ClipboardTest test6;
    QTest::qExec(&test6);
}
