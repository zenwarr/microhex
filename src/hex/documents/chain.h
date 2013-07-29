#ifndef CHAIN_H
#define CHAIN_H

#include <QObject>
#include <QList>

class AbstractSpan;
class DeviceSpan;

typedef QList< AbstractSpan* > SpanList;

class SpanChain : public QObject {
    friend class DeviceSpan;
public:
    SpanChain(const SpanList &spans=SpanList());
    ~SpanChain();

    qulonglong length()const;

    const SpanList &spans()const;
    void setSpans(const SpanList &spans);
    void clear();

    QByteArray read(qulonglong offset, qulonglong length)const;
    QByteArray readAll()const;
    SpanList spansInRange(qulonglong offset, qulonglong length, qulonglong *left_offset=0,
                          qulonglong *right_offset=0)const;
    int findSpanIndex(qulonglong offset, qulonglong *span_offset=0)const;
    AbstractSpan* spanAtOffset(qulonglong offset, qulonglong *span_offset=0)const;
    SpanList takeSpans(qulonglong offset, qulonglong length);
    void splitSpans(qulonglong offset);

    void insertSpan(qulonglong offset, AbstractSpan *span);
    void insertChain(qulonglong offset, SpanChain *chain);
    void remove(qulonglong offset, qulonglong length);

    static SpanChain *fromSpans(const SpanList &spans);

protected:
    void _dissolveSpan(AbstractSpan *span, const SpanList &replacement);

private:
    qulonglong _calculateLength(const SpanList &spans);
    SpanList _privatizeSpans(const SpanList &spans);

    SpanList _spans;
    qulonglong _length;
};

#endif // CHAIN_H
