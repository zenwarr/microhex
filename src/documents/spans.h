#ifndef SPANS_H
#define SPANS_H

#include <QByteArray>
#include <QPair>
#include <QObject>
#include <QMetaType>
#include <memory>

class SpanChain;
class AbstractDevice;
class AbstractSaver;
class AbstractSpan;

typedef QList<std::shared_ptr<AbstractSpan>> SpanList;

class AbstractSpan : public QObject, public std::enable_shared_from_this<AbstractSpan> {
    Q_OBJECT
public:
    AbstractSpan();
    ~AbstractSpan();

    virtual qulonglong getLength()const = 0;
    virtual QByteArray read(qulonglong offset, qulonglong length)const = 0;
    virtual QPair<std::shared_ptr<AbstractSpan>, std::shared_ptr<AbstractSpan>> split(qulonglong offset)const = 0;
    virtual void put(const std::shared_ptr<AbstractSaver> &saver)const;

signals:
    void dissolved(const std::shared_ptr<AbstractSpan> &span, const SpanList &replacement);

protected:
    bool _isRangeValid(qulonglong offset, qulonglong size)const;
};


class DataSpan : public AbstractSpan {
public:
    DataSpan(const QByteArray &data);

    qulonglong getLength()const { return _data.length(); }
    QByteArray read(qulonglong offset, qulonglong length)const;
    QPair<std::shared_ptr<AbstractSpan>, std::shared_ptr<AbstractSpan>> split(qulonglong offset)const;

private:
    QByteArray _data;
};


class FillSpan : public AbstractSpan {
public:
    FillSpan(qulonglong repeat_count, char fill_byte);

    qulonglong getLength()const;
    QByteArray read(qulonglong offset, qulonglong length)const;
    QPair<std::shared_ptr<AbstractSpan>, std::shared_ptr<AbstractSpan>> split(qulonglong offset)const;

private:
    char _fillByte;
    qulonglong _repeatCount;
};


class PrimitiveDeviceSpan : public AbstractSpan {
    friend class AbstractDevice;
public:
    ~PrimitiveDeviceSpan();

    qulonglong getLength()const;
    QByteArray read(qulonglong offset, qulonglong length)const;
    QPair<std::shared_ptr<AbstractSpan>, std::shared_ptr<AbstractSpan>> split(qulonglong offset)const;

    std::shared_ptr<const AbstractDevice> getDevice()const { return _device; }
    qulonglong getDeviceOffset()const { return _deviceOffset; }

    void prepareToDissolve(const QList<std::shared_ptr<AbstractSpan>> &replacement);
    void cancelDissolve(); // should never throw!
    void dissolve();

private:
    std::shared_ptr<AbstractDevice> _device;
    qulonglong _deviceOffset;
    qulonglong _length;
    QList<std::shared_ptr<AbstractSpan>> _dissolvingTo;

    PrimitiveDeviceSpan(const std::shared_ptr<AbstractDevice> &device, qulonglong deviceOffset, qulonglong length);
};


class DeviceSpan : public AbstractSpan {
public:
    DeviceSpan(const std::shared_ptr<AbstractDevice> &device, qulonglong deviceOffset, qulonglong length);
    ~DeviceSpan();

    qulonglong getLength()const;
    QByteArray read(qulonglong offset, qulonglong length)const;
    QPair<std::shared_ptr<AbstractSpan>, std::shared_ptr<AbstractSpan>> split(qulonglong offset)const;

    QMap<std::shared_ptr<PrimitiveDeviceSpan>, qulonglong> getPrimitives()const;
    QList<std::shared_ptr<AbstractSpan>> getSpans()const;
    void put(const std::shared_ptr<AbstractSaver> &saver) const;

private:
    std::shared_ptr<SpanChain> _chain;

    DeviceSpan(const std::shared_ptr<SpanChain> &chain);
};


Q_DECLARE_METATYPE(SpanList)
Q_DECLARE_METATYPE(std::shared_ptr<AbstractSpan>)

#endif // SPANS_H
