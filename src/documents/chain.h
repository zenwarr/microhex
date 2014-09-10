#ifndef CHAIN_H
#define CHAIN_H

#include <QObject>
#include <QList>
#include <memory>
#include "readwritelock.h"
#include "spans.h"

class AbstractSpan;
class DeviceSpan;
class PrimitiveDeviceSpan;

class SpanChain : public QObject, public std::enable_shared_from_this<SpanChain> {
    Q_OBJECT
    class SpanData;
    friend class SpanChain::SpanData;
public:
    SpanChain();
    ~SpanChain();

    qulonglong getLength()const;
    const std::shared_ptr<ReadWriteLock> &getLock()const { return _lock; }

    SpanList getSpans()const;
    void setSpans(const SpanList &spans);
    void clear();

    QByteArray read(qulonglong offset, qulonglong length)const;
    QByteArray readAll()const;

    SpanList spansInRange(qulonglong offset, qulonglong length, qulonglong *left_offset=nullptr,
                          qulonglong *right_offset=nullptr)const;
    SpanList takeSpans(qulonglong offset, qulonglong length);
    std::shared_ptr<SpanChain> takeChain(qulonglong offset, qulonglong length)const;
    std::shared_ptr<SpanChain> exportRange(qulonglong offset, qulonglong length, int ram_limit=-1)const;

    std::shared_ptr<AbstractSpan> spanAtOffset(qulonglong offset, qulonglong *span_offset=nullptr)const;
    void splitSpans(qulonglong offset);

    void insertSpan(qulonglong offset, const std::shared_ptr<AbstractSpan> &span);
    void insertChain(qulonglong offset, const std::shared_ptr<SpanChain> &chain);
    void remove(qulonglong offset, qulonglong length);

    void setCommonSavepoint(int savepoint);
    int spanSavepoint(const std::shared_ptr<AbstractSpan> &span);

    SpanChain &operator=(const SpanChain &other);

    static std::shared_ptr<SpanChain> fromSpans(const SpanList &spans);
    static std::shared_ptr<SpanChain> fromChain(const SpanChain &chain);

private slots:
    void _onSpanDissolved(const std::shared_ptr<AbstractSpan> &span, const SpanList &replacement);

private:
    struct SpanData {
        SpanData() : savepoint(-1), connected(false) { }
        SpanData(const std::shared_ptr<SpanChain> &chain, const std::shared_ptr<AbstractSpan> &span, int savepoint=-1);
        SpanData(const std::shared_ptr<SpanChain> &chain, const SpanData &other);
        ~SpanData();

        std::shared_ptr<AbstractSpan> span;
        std::weak_ptr<SpanChain> chain; // equals to SpanChain where this span lives
        int savepoint;
        bool connected;

    private:
        void connect();
    };

    qulonglong _calculateLength(const SpanList &spans);
    int _findSpanIndex(qulonglong offset, qulonglong *span_offset=nullptr)const;
    void _setSpans(const QList<std::shared_ptr<SpanData>> &);
    SpanList _spanDataListToSpans(const QList<std::shared_ptr<SpanData>> &list) const;

    QList<std::shared_ptr<SpanData>> _spans;
    qulonglong _length;
    std::shared_ptr<ReadWriteLock> _lock;
};

#endif // CHAIN_H
