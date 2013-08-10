#ifndef MATCHER_H
#define MATCHER_H

#include <QByteArray>
#include <memory>
#include "base.h"

class Document;


class BinaryFinder {
public:
    BinaryFinder(const std::shared_ptr<Document> &doc, const QByteArray &findWhat);

    qulonglong findNext(qulonglong from_position, qulonglong limit=QULONGLONG_MAX, bool *found=nullptr);
    qulonglong findPrevious(qulonglong from_position, qulonglong limit=QULONGLONG_MAX, bool *found=nullptr);

private:
    std::shared_ptr<Document> _document;
    QByteArray _findWhat;
    QByteArray _offsetTable;
    QByteArray _reversedOffsetTable;
};


#endif // MATCHER_H
