#include "chain.h"
#include <cassert>
#include <climits>
#include <algorithm>
#include <functional>
#include "spans.h"
#include "devices.h"
#include "base.h"


SpanChain::SpanChain() : _length(), _lock(std::make_shared<ReadWriteLock>()) {

}

SpanChain &SpanChain::operator=(const SpanChain &other) {
    _setSpans(other._spans);
    return *this;
}

std::shared_ptr<SpanChain> SpanChain::fromSpans(const SpanList &spans) {
    auto chain = std::make_shared<SpanChain>();
    chain->setSpans(spans);
    return chain;
}

std::shared_ptr<SpanChain> SpanChain::fromChain(const SpanChain &chain) {
    auto new_chain = std::make_shared<SpanChain>();
    new_chain->_setSpans(chain._spans);
    return new_chain;
}

SpanChain::~SpanChain() {

}

qulonglong SpanChain::getLength() const {
    return _length;
}

SpanList SpanChain::getSpans() const {
    ReadLocker locker(_lock);
    return _spanDataListToSpans(_spans);
}

void SpanChain::setSpans(const SpanList &spans) {
    WriteLocker locker(_lock);

    QList<std::shared_ptr<SpanData>> new_list;
    qulonglong new_length = _calculateLength(spans);
    for (auto span : spans) {
        new_list.append(std::make_shared<SpanData>(shared_from_this(), span));
    }

    std::swap(new_list, _spans);
    std::swap(new_length, _length);
}

void SpanChain::_setSpans(const QList<std::shared_ptr<SpanChain::SpanData>> &spans) {
    WriteLocker locker(_lock);

    QList<std::shared_ptr<SpanData>> new_list;
    qulonglong new_length = 0;
    for (auto span_data : spans) {
        new_list.append(std::make_shared<SpanData>(shared_from_this(), *span_data));
        if (new_length + span_data->span->getLength() < new_length) {
            throw std::overflow_error("integer overflow");
        }
        new_length += span_data->span->getLength();
    }

    std::swap(new_list, _spans);
    std::swap(new_length, _length);
}

void SpanChain::clear() {
    setSpans(SpanList());
}

QByteArray SpanChain::read(qulonglong offset, qulonglong length) const {
    /** Read as much data as possible starting from :offset:, but not more than :length: bytes.
     */
    ReadLocker locker(_lock);

    if (offset > _length) {
        return QByteArray();
    } else if (offset + length > _length) {
        length = _length - offset;
    } else if (length > qulonglong(INT_MAX)) {
        throw std::overflow_error("integer overflow");
    }

    qulonglong left_offset, right_offset;
    SpanList spans = spansInRange(offset, length, &left_offset, &right_offset);
    QByteArray result;
    for (int span_index = 0; span_index < spans.length(); ++span_index) {
        qulonglong pos = !span_index ? left_offset : 0;
        qulonglong size = span_index == spans.length() - 1 ? (right_offset - pos) + 1 : spans[span_index]->getLength() - pos;
        size = std::min(size, length - result.length());
        result += spans[span_index]->read(pos, size);
    }
    return result;
}

QByteArray SpanChain::readAll() const {
    ReadLocker locker(_lock);
    return read(0, this->getLength());
}

SpanList SpanChain::spansInRange(qulonglong offset, qulonglong length, qulonglong *left_offset,
                                 qulonglong *right_offset) const {
    /** Returns list of spans that contain :length: of bytes from :offset:. It is not guarantied that first
     *  span in returned list starts at :offset: or last span ends at :offset: + :length: - 1. You can additionally
     *  get :left_offset: (number of bytes between first byte of first returned span and byte at :offset:, including
     *  first byte) and :right_offset: (number of bytes between first byte of last returned span and byte at :offset:,
     *  including first byte).
     **/

    ReadLocker locker(_lock);

    if (left_offset) {
        *left_offset = 0;
    }
    if (right_offset) {
        *right_offset = 0;
    }

    if (offset + length > _length) {
        length = _length - offset;
    }

    if (_spans.isEmpty() || !length) {
        return SpanList();
    }

    int first_span_index = _findSpanIndex(offset, left_offset),
        last_span_index = _findSpanIndex(offset + length - 1, right_offset);
    assert(first_span_index >= 0 && last_span_index >= 0);

    return _spanDataListToSpans(_spans.mid(first_span_index, last_span_index - first_span_index + 1));
}

int SpanChain::_findSpanIndex(qulonglong offset, qulonglong *span_offset) const {
    /** Same as SpanChain::spanAtOffset function, but returns index of span in _spans list
     **/
    ReadLocker locker(_lock);

    if (span_offset) {
        *span_offset = 0;
    }

    if (_spans.isEmpty() || offset >= _length) {
        return -1;
    }

    qulonglong current_offset = 0;
    for (int j = 0; j < _spans.length(); ++j) {
        if (offset >= current_offset && offset < current_offset + _spans[j]->span->getLength()) {
            if (span_offset) {
                *span_offset = offset - current_offset;
            }
            return j;
        }
        current_offset += _spans[j]->span->getLength();
    }

    return -1;
}

std::shared_ptr<AbstractSpan> SpanChain::spanAtOffset(qulonglong offset, qulonglong *span_offset) const {
    /** Looks for span that holds byte at :offset:, additionally can return :span_offset: which indicates
     *  number of bytes between first byte of returned span and :offset:, including first byte. If :offset:
     *  is out of bounds, -1 is returned and :span_offset: is initialized to 0.
     **/

    ReadLocker locker(_lock);

    int span_index = _findSpanIndex(offset, span_offset);
    return span_index >= 0 ? _spans[span_index]->span : nullptr;
}

SpanList SpanChain::takeSpans(qulonglong offset, qulonglong length) {
    /** Same as SpanChain::spansInRange, but first splits chain at :offset: and :offset: + :length:, so
     *  it is guaranteed that first span in returned list holds byte at :offset: and last span holds
     *  byte at :offset: + :length: - 1
     **/

    WriteLocker locker(_lock);

    if (offset >= _length) {
        return SpanList();
    } else if (offset + length > _length) {
        length = _length - offset;
    }

    if (_spans.isEmpty() || !length) {
        return SpanList();
    }

    splitSpans(offset);
    splitSpans(offset + length);
    return spansInRange(offset, length);
}

std::shared_ptr<SpanChain> SpanChain::takeChain(qulonglong offset, qulonglong length) const {
    ReadLocker locker(_lock);

    if (offset >= _length) {
        return std::make_shared<SpanChain>();
    } else if (offset + length > _length) {
        length = _length - offset;
    }

    if (_spans.isEmpty() || !length) {
        return std::make_shared<SpanChain>();
    }

    auto result = SpanChain::fromChain(*this);
    result->remove(0, offset);
    result->remove(length, result->getLength() - length);

    return result;
}

std::shared_ptr<SpanChain> SpanChain::exportRange(qulonglong offset, qulonglong length, int ram_limit)const {
    // just like takeSpans, but this chain remains unchanged.
    ReadLocker locker(_lock);

    auto result = takeChain(offset, length);

    // now we can replace DeviceSpans with DataSpans to keep data safe (as device data can be
    // changed externally). If ram_limit is -1, we will allocate as much memory as possible, if
    // ram_limit == 0 - we will not convert DeviceSpans to DataSpans at all. Note that ram_limit limites only
    // amount of memory occupied by created DataSpans data, not by all chain.
    if (ram_limit != 0) {
        int current_ram = 0;
        // iterate over spans in resulting chain
        for (int j = 0; j < result->_spans.length(); ++j) {
            auto device_span = std::dynamic_pointer_cast<DeviceSpan>(result->_spans.at(j)->span);
            if (device_span) {
                // check if amount of already used memory allows us to convert current device span to DataSpan
                if (ram_limit < 0 || qulonglong(current_ram) + device_span->getLength() <= qulonglong(ram_limit)) {
                    QByteArray data = device_span->read(0, device_span->getLength());
                    assert(qulonglong(data.length()) == device_span->getLength());
                    result->_spans[j]->span = std::make_shared<DataSpan>(data);
                    current_ram += data.length();
                }
            }
        }
    }

    result->setCommonSavepoint(-1);
    return result;
}

void SpanChain::setCommonSavepoint(int savepoint) {
    /** Sets savepoint index for all spans.
     **/
    for (auto span_data : _spans) {
        span_data->savepoint = savepoint;
    }
}

int SpanChain::spanSavepoint(const std::shared_ptr<AbstractSpan> &span) {
    /** Returns savepoint for :span:, if span is in chain; otherwise returns -1
     **/
    for (auto span_data : _spans) {
        if (span_data->span == span) {
            return span_data->savepoint;
        }
    }
    return -1;
}

void SpanChain::splitSpans(qulonglong offset) {
    /** After calling this function you can be sure that there is boundary between spans at :offset:. It means that
        byte at :offset: is first byte of span (if exists). If :offset: is invalid, function has no effect.
    */
    WriteLocker locker(_lock);

    qulonglong span_offset = 0;
    int span_index = _findSpanIndex(offset, &span_offset);
    if (span_index >= 0 && span_offset) {
        int savepoint = _spans[span_index]->savepoint;
        auto splitted = _spans[span_index]->span->split(span_offset);
        _spans.replace(span_index, std::make_shared<SpanData>(shared_from_this(), splitted.first, savepoint));
        _spans.insert(span_index + 1, std::make_shared<SpanData>(shared_from_this(), splitted.second, savepoint));
    }
}

void SpanChain::insertSpan(qulonglong offset, const std::shared_ptr<AbstractSpan> &span) {
    insertChain(offset, SpanChain::fromSpans(SpanList() << span));
}

void SpanChain::insertChain(qulonglong offset, const std::shared_ptr<SpanChain> &chain) {
    /** Inserts data from :chain: into this chain. Savepoints from :chain: are copied too.
     *  If :offset: equals to length of this chain, data is appended, if :offset: is greater than this
     *  chain length, OutOfBoundsError will be thrown.
     **/

    WriteLocker locker(_lock);

    int span_index; // index of span before which we will insert our chain
    if (_length + chain->getLength() < _length) {
        throw std::overflow_error("integer overflow");
    } else if (offset > _length) {
        throw OutOfBoundsError();
    } else if (offset < _length) {
        splitSpans(offset);
        span_index = _findSpanIndex(offset);
    } else {
        // offset == _length
        span_index = _spans.length();
    }

    QList<std::shared_ptr<SpanData>> new_list = _spans;
    qulonglong new_length = _length + chain->getLength();

    for (auto span_data : chain->_spans) {
        new_list.insert(span_index++, std::shared_ptr<SpanData>(new SpanData(shared_from_this(), *span_data)));
    }

    std::swap(new_list, _spans);
    std::swap(new_length, _length);
}

void SpanChain::remove(qulonglong offset, qulonglong length) {
    /** Removes exactly :length: bytes starting from :offset:. If :length: bytes cannot be removed,
     *  OutOfBoundsError will be thrown.
     **/

    WriteLocker locker(_lock);

    if (length && (offset >= _length || offset + length > _length)) {
        throw OutOfBoundsError();
    }

    if (!length) {
        return;
    }

    auto removed_spans = takeSpans(offset, length);
    int span_index = _findSpanIndex(offset);
    for (int j = 0; j < removed_spans.length(); ++j) {
        _spans.removeAt(span_index);
    }
    _length -= length;
}

void SpanChain::_onSpanDissolved(const std::shared_ptr<AbstractSpan> &span, const SpanList &replacement) {
    WriteLocker locker(_lock);

    assert(span->getLength() == _calculateLength(replacement));

    auto span_iter = std::find_if(_spans.constBegin(), _spans.constEnd(),
                                  [span](const std::shared_ptr<SpanData> &d) { return d->span == span; });
    if (span_iter == _spans.constEnd()) {
        return;
    }

    int span_index = span_iter - _spans.constBegin();
    if (span_index >= 0) {
        auto removed_span_data = _spans.takeAt(span_index);
        ++span_index;
        for (int j = 0; j < replacement.length(); ++j, ++span_index) {
            auto span_data = std::make_shared<SpanData>(shared_from_this(), replacement.at(j));
            span_data->savepoint = removed_span_data->savepoint;
            _spans.insert(span_index, span_data);
        }
    }
}

qulonglong SpanChain::_calculateLength(const SpanList &spans) {
    qulonglong result = 0;
    for (auto span : spans) {
        if (result + span->getLength() < result) {
            throw std::overflow_error("integer overflow");
        } else {
            result += span->getLength();
        }
    }
    return result;
}

SpanList SpanChain::_spanDataListToSpans(const QList<std::shared_ptr<SpanChain::SpanData>> &list)const {
    SpanList result;
    std::transform(list.constBegin(), list.constEnd(), std::back_inserter(result),
                   [](const std::shared_ptr<SpanData> &data) { return data->span; });
    return result;
}

SpanChain::SpanData::SpanData(const std::shared_ptr<SpanChain> &chain, const std::shared_ptr<AbstractSpan> &span,
                              int savepoint)
    : span(span), chain(chain), savepoint(savepoint), connected(false) {
    connect();
}

SpanChain::SpanData::SpanData(const std::shared_ptr<SpanChain> &chain, const SpanChain::SpanData &other)
    : span(other.span), chain(chain), savepoint(other.savepoint), connected(false) {
    connect();
}

SpanChain::SpanData::~SpanData() {
    if (connected) {
        auto locked = chain.lock();
        if (locked) {
            QObject::disconnect(span.get(),
                                SIGNAL(dissolved(const std::shared_ptr<AbstractSpan> &, const SpanList &)),
                                locked.get(),
                                SLOT(_onSpanDissolved(const std::shared_ptr<AbstractSpan> &, const SpanList &)));
        }
    }
}

void SpanChain::SpanData::connect() {
    if (span) {
        auto locked = chain.lock();
        if (locked) {
            QObject::connect(span.get(),
                             SIGNAL(dissolved(const std::shared_ptr<AbstractSpan> &, const SpanList &)),
                             locked.get(),
                             SLOT(_onSpanDissolved(const std::shared_ptr<AbstractSpan> &, const SpanList &)));
            connected = true;
        }
    }
}
