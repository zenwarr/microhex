#ifndef SPANS_H
#define SPANS_H

#include <QByteArray>
#include <QPair>

class SpanChain;
class AbstractDevice;

class AbstractSpan : public QObject {
    Q_OBJECT
public:
    AbstractSpan();
    ~AbstractSpan();

    virtual qulonglong length()const = 0;
    virtual QByteArray read(qulonglong offset, qulonglong length)const = 0;
    virtual QPair<AbstractSpan*, AbstractSpan*> split(qulonglong offset)const;
    virtual AbstractSpan *clone()const = 0;
    SpanChain *parentChain()const;

    qulonglong savepoint;

protected:
    bool _isRangeValid(qulonglong offset, qulonglong size)const;

private:
    Q_DISABLE_COPY(AbstractSpan)
};


class DataSpan : public AbstractSpan {
public:
    DataSpan(const QByteArray &data);

    qulonglong length()const { return _data.length(); }
    QByteArray read(qulonglong offset, qulonglong length)const;
    QPair<AbstractSpan*, AbstractSpan*> split(qulonglong offset) const;
    AbstractSpan* clone()const;

private:
    QByteArray _data;
};


class FillSpan : public AbstractSpan {
public:
    FillSpan(char fill_byte, int repeat_count);

    qulonglong length()const;
    QByteArray read(qulonglong offset, qulonglong length) const;
    QPair<AbstractSpan*, AbstractSpan*> split(qulonglong offset) const;
    AbstractSpan* clone()const;

private:
    char _fillByte;
    int _repeatCount;
};


class DeviceSpan : public AbstractSpan {
    friend class AbstractDevice;
public:
    DeviceSpan(const AbstractDevice *device, qulonglong deviceOffset, qulonglong length);
    ~DeviceSpan();

    qulonglong length()const;
    QByteArray read(qulonglong offset, qulonglong length) const;
    QPair< AbstractSpan*, AbstractSpan* > split(qulonglong offset) const;
    AbstractSpan* clone()const;
    const AbstractDevice *device()const { return _device; }
    qulonglong deviceOffset()const { return _deviceOffset; }
    void adjust(const AbstractDevice *device, qulonglong device_offset);

    void prepareToDissolve(const AbstractDevice *new_device, const QList<AbstractSpan*> &replacement);
    void cancelDissolve();
    void dissolve();

private:
    const AbstractDevice *_device;
    qulonglong _deviceOffset;
    qulonglong _length;
    const AbstractDevice *_dissolvingToDevice;
    QList<AbstractSpan*> _dissolvingTo;
};

#endif // SPANS_H
