#include "spans.h"
#include <climits>
#include <exception>
#include <memory>
#include "chain.h"
#include "devices.h"

AbstractSpan::AbstractSpan() {

}

AbstractSpan::~AbstractSpan() {

}

void AbstractSpan::put(const std::shared_ptr<AbstractSaver> &saver) const {
    saver->putSpan(shared_from_this());
}

bool AbstractSpan::_isRangeValid(qulonglong offset, qulonglong size)const {
    return offset < this->getLength() && offset + size <= this->getLength();
}

DataSpan::DataSpan(const QByteArray &data) : _data(data) {

}

QByteArray DataSpan::read(qulonglong offset, qulonglong length) const {
    if (!_isRangeValid(offset, length)) {
        throw OutOfBoundsError();
    } else if (offset > qulonglong(INT_MAX) || length > qulonglong(INT_MIN)) {
        throw std::overflow_error("integer overflow");
    }
    return _data.mid(int(offset), int(length));
}

QPair<std::shared_ptr<AbstractSpan>, std::shared_ptr<AbstractSpan>> DataSpan::split(qulonglong offset) const {
    if (offset == 0 || offset >= getLength()) {
        throw OutOfBoundsError();
    }
    auto f = std::make_shared<DataSpan>(_data.mid(0, int(offset))),
         s = std::make_shared<DataSpan>(_data.mid(int(offset), -1));
    return qMakePair(std::shared_ptr<AbstractSpan>(f), std::shared_ptr<AbstractSpan>(s));
}

FillSpan::FillSpan(qulonglong repeat_count, char fill_byte) : _fillByte(fill_byte), _repeatCount(repeat_count) {

}

qulonglong FillSpan::getLength() const {
    return _repeatCount;
}

QByteArray FillSpan::read(qulonglong offset, qulonglong length) const {
    if (!_isRangeValid(offset, length)) {
        throw OutOfBoundsError();
    } else if (length > qulonglong(INT_MAX)) {
        throw std::overflow_error("integer overflow");
    }
    return QByteArray(length, _fillByte);
}

QPair<std::shared_ptr<AbstractSpan>, std::shared_ptr<AbstractSpan>> FillSpan::split(qulonglong offset) const {
    if (offset == 0 || offset >= getLength()) {
        throw OutOfBoundsError();
    }

    auto f = std::make_shared<FillSpan>(offset, _fillByte),
         s = std::make_shared<FillSpan>(_repeatCount - offset, _fillByte);
    return qMakePair(std::shared_ptr<AbstractSpan>(f),
                     std::shared_ptr<AbstractSpan>(s));
}

PrimitiveDeviceSpan::PrimitiveDeviceSpan(const std::shared_ptr<AbstractDevice> &device, qulonglong deviceOffset, qulonglong length)
    : _device(device), _deviceOffset(deviceOffset), _length(length) {

}

PrimitiveDeviceSpan::~PrimitiveDeviceSpan() {
    _device->_removeSpan(this);
}

qulonglong PrimitiveDeviceSpan::getLength() const {
    return _length;
}

QByteArray PrimitiveDeviceSpan::read(qulonglong offset, qulonglong length) const {
    if (!_isRangeValid(offset, length) || offset >= _device->getLength() || _device->getLength() - length < offset) {
        throw OutOfBoundsError();
    } else if (length > qulonglong(INT_MAX)) {
        throw std::overflow_error("integer overflow");
    }

    QByteArray read_data = _device->read(_deviceOffset + offset, length);
    qulonglong read_bytes_count = std::max(0, read_data.length());
    if (read_bytes_count < length) {
        return read_data + QByteArray(static_cast<int>(length - read_bytes_count), 0);
    } else {
        return read_data;
    }
}

QPair<std::shared_ptr<AbstractSpan>, std::shared_ptr<AbstractSpan> > PrimitiveDeviceSpan::split(qulonglong offset) const {
    if (!offset || offset >= getLength()) {
        throw OutOfBoundsError();
    }

    auto f = _device->createSpan(_deviceOffset, offset),
            s = _device->createSpan(_deviceOffset + offset, _length - offset);
    return qMakePair(std::shared_ptr<AbstractSpan>(f), std::shared_ptr<AbstractSpan>(s));
}

void PrimitiveDeviceSpan::prepareToDissolve(const QList<std::shared_ptr<AbstractSpan>> &replacement) {
    _dissolvingTo = replacement;
}

void PrimitiveDeviceSpan::cancelDissolve() {
    _dissolvingTo.clear();
}

void PrimitiveDeviceSpan::dissolve() {
    emit dissolved(shared_from_this(), _dissolvingTo); // we need to pass reference to this every time because
                                                       // QObject::sender does not work for queued connections
}

DeviceSpan::DeviceSpan(const std::shared_ptr<AbstractDevice> &device, qulonglong deviceOffset, qulonglong length) {
    auto span_list = SpanList() << device->createSpan(deviceOffset, length);
    _chain = SpanChain::fromSpans(span_list);
}

DeviceSpan::~DeviceSpan() {

}

qulonglong DeviceSpan::getLength() const {
    return _chain->getLength();
}

QByteArray DeviceSpan::read(qulonglong offset, qulonglong length) const {
    if (!_isRangeValid(offset, length)) {
        throw OutOfBoundsError();
    }
    return _chain->read(offset, length);
}

QPair<std::shared_ptr<AbstractSpan>, std::shared_ptr<AbstractSpan> > DeviceSpan::split(qulonglong offset) const {
    if (!offset || offset >= getLength()) {
        throw OutOfBoundsError();
    }

    auto f = std::shared_ptr<DeviceSpan>(new DeviceSpan(_chain->exportRange(0, offset, 0))),
         s = std::shared_ptr<DeviceSpan>(new DeviceSpan(_chain->exportRange(offset, _chain->getLength() - offset, 0)));
    return qMakePair(std::shared_ptr<AbstractSpan>(f), std::shared_ptr<AbstractSpan>(s));
}

QMap<std::shared_ptr<PrimitiveDeviceSpan>, qulonglong> DeviceSpan::getPrimitives() const {
    QMap<std::shared_ptr<PrimitiveDeviceSpan>, qulonglong> result;
    qulonglong position = 0;
    for (auto span : _chain->getSpans()) {
        if (std::dynamic_pointer_cast<PrimitiveDeviceSpan>(span)) {
            result[std::dynamic_pointer_cast<PrimitiveDeviceSpan>(span)] = position;
        }
        position += span->getLength();
    }
    return result;
}

QList<std::shared_ptr<AbstractSpan>> DeviceSpan::getSpans() const {
    return _chain->getSpans();
}

void DeviceSpan::put(const std::shared_ptr<AbstractSaver> &saver) const {
    for (auto span : _chain->getSpans()) {
        saver->putSpan(span);
    }
}

DeviceSpan::DeviceSpan(const std::shared_ptr<SpanChain> &chain) : _chain(chain) {

}
