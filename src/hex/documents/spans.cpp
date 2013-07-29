#include "spans.h"
#include <climits>
#include <exception>
#include "chain.h"
#include "devices.h"

AbstractSpan::AbstractSpan() : savepoint() {

}

AbstractSpan::~AbstractSpan() {

}

QPair<AbstractSpan *, AbstractSpan *> AbstractSpan::split(qulonglong offset) const {
    Q_UNUSED(offset);
    throw std::exception();
}

bool AbstractSpan::_isRangeValid(qulonglong offset, qulonglong size)const {
    return offset < this->length() && offset + size <= this->length();
}

SpanChain *AbstractSpan::parentChain() const {
    return dynamic_cast<SpanChain*>(parent());
}

DataSpan::DataSpan(const QByteArray &data)
    : AbstractSpan(), _data(data) {

}

QByteArray DataSpan::read(qulonglong offset, qulonglong length) const {
    if (!_isRangeValid(offset, length)) {
        throw OutOfBoundsError();
    } else if (offset > qulonglong(INT_MAX) || length > qulonglong(INT_MIN)) {
        throw OutOfBoundsError();
    }
    return _data.mid(int(offset), int(length));
}

QPair<AbstractSpan*, AbstractSpan* > DataSpan::split(qulonglong offset) const {
    if (offset == 0 || offset >= length() || offset > INT_MAX) {
        throw OutOfBoundsError();
    }
    AbstractSpan *f = new DataSpan(_data.mid(0, int(offset))),
                 *s = new DataSpan(_data.mid(int(offset), -1));
    f->savepoint = s->savepoint = savepoint;
    return qMakePair(f, s);
}

AbstractSpan* DataSpan::clone() const {
    auto span = new DataSpan(_data);
    span->savepoint = savepoint;
    return span;
}

FillSpan::FillSpan(char fill_byte, int repeat_count)
    : AbstractSpan(), _fillByte(fill_byte), _repeatCount(repeat_count) {

}

qulonglong FillSpan::length() const {
    return _repeatCount;
}

QByteArray FillSpan::read(qulonglong offset, qulonglong length) const {
    if (!_isRangeValid(offset, length) || offset > INT_MAX || length > INT_MAX) {
        throw OutOfBoundsError();
    }
    return QByteArray(length, _fillByte);
}

QPair<AbstractSpan*, AbstractSpan* > FillSpan::split(qulonglong offset) const {
    if (offset == 0 || offset >= length()) {
        throw OutOfBoundsError();
    }
    AbstractSpan *f = new FillSpan(_fillByte, offset),
                 *s = new FillSpan(_fillByte, _repeatCount - offset);
    f->savepoint = s->savepoint = savepoint;
    return qMakePair(f, s);
}

AbstractSpan* FillSpan::clone() const {
    auto span = new FillSpan(_fillByte, _repeatCount);
    span->savepoint = savepoint;
    return span;
}

DeviceSpan::DeviceSpan(const AbstractDevice *device, qulonglong deviceOffset, qulonglong length)
    : _device(device), _deviceOffset(deviceOffset), _length(length) {
    _device->_addSpan(this);
}

DeviceSpan::~DeviceSpan() {
    _device->_removeSpan(this);
}

qulonglong DeviceSpan::length() const {
    return _length;
}

QByteArray DeviceSpan::read(qulonglong offset, qulonglong length) const {
    if (!_isRangeValid(offset, length) || offset >= _device->length() || offset + length > _device->length()) {
        throw OutOfBoundsError();
    }
    QByteArray read_data = _device->read(_deviceOffset + offset, length);
    qulonglong read_bytes_count = std::max(0, read_data.length());
    if (read_bytes_count < length) {
        return read_data + QByteArray(static_cast<int>(length - read_bytes_count), 0);
    } else {
        return read_data;
    }
}

QPair<AbstractSpan*, AbstractSpan* > DeviceSpan::split(qulonglong offset) const {
    if (!offset || offset >= length()) {
        throw OutOfBoundsError();
    }
    AbstractSpan *f = new DeviceSpan(_device, _deviceOffset, offset),
                 *s = new DeviceSpan(_device, _deviceOffset + offset, _length - offset);
    f->savepoint = s->savepoint = savepoint;
    return qMakePair(f, s);
}

AbstractSpan* DeviceSpan::clone() const {
    auto cloned = new DeviceSpan(_device, _deviceOffset, _length);
    cloned->savepoint = savepoint;
    return cloned;
}

void DeviceSpan::adjust(const AbstractDevice *device, qulonglong device_offset) {
    if (_device != device) {
        _device->_removeSpan(this);
        _device = device;
        _device->_addSpan(this);
    }
    _deviceOffset = device_offset;
}

void DeviceSpan::prepareToDissolve(const AbstractDevice *new_device, const QList< AbstractSpan* > &replacement) {
    _dissolvingToDevice = new_device;
    _dissolvingTo = replacement;
}

void DeviceSpan::cancelDissolve() {
    _dissolvingToDevice = nullptr;
    _dissolvingTo.clear();
}

void DeviceSpan::dissolve() {
    if (!_dissolvingTo.isEmpty()) {
        for (int j = 0; j < _dissolvingTo.length(); ++j) {
            DeviceSpan *deviceSpan = dynamic_cast<DeviceSpan*>(_dissolvingTo[j]);
            if (deviceSpan) {
                deviceSpan->adjust(_dissolvingToDevice, deviceSpan->deviceOffset());
            }
        }
        if (parentChain()) {
            parentChain()->_dissolveSpan(this, _dissolvingTo);
        }
    }
}

