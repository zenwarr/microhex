#include "chain.h"
#include <cassert>
#include <QDebug>
#include "spans.h"
#include "devices.h"


SpanChain::SpanChain(const SpanList &spans) : _length() {
    setSpans(spans);
}

SpanChain::~SpanChain() {

}

qulonglong SpanChain::length() const {
    return _length;
}

const SpanList &SpanChain::spans() const {
    return _spans;
}

void SpanChain::setSpans(const SpanList &spans) {
    if (spans != _spans) {
        auto replaced_spans = _spans;
        _spans = _privatizeSpans(spans);
        _length = _calculateLength(_spans);
        for (auto span : replaced_spans) {
            if (!_spans.contains(span)) {
                delete span;
            }
        }
    }
}

void SpanChain::clear() {
    setSpans(SpanList());
}

QByteArray SpanChain::read(qulonglong offset, qulonglong length) const {
    if (offset > _length) {
        return QByteArray();
    } else if (offset + length > _length) {
        length = _length - offset;
    }

    qulonglong left_offset, right_offset;
    SpanList spans = spansInRange(offset, length, &left_offset, &right_offset);
    QByteArray result;
    for (int span_index = 0; span_index < spans.length(); ++span_index) {
        qulonglong pos = !span_index ? left_offset : 0;
        qulonglong size = span_index == spans.length() - 1 ? (right_offset - pos) + 1 : spans[span_index]->length() - pos;
        size = std::min(size, length - result.length());
        result += spans[span_index]->read(pos, size);
    }
    return result;
}

QByteArray SpanChain::readAll() const {
    return read(0, this->length());
}

SpanList SpanChain::spansInRange(qulonglong offset, qulonglong length, qulonglong *left_offset,
                                 qulonglong *right_offset) const {
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

    int first_span_index = findSpanIndex(offset, left_offset),
        last_span_index = findSpanIndex(offset + length - 1, right_offset);
    assert(first_span_index >= 0 && last_span_index >= 0);
    return _spans.mid(first_span_index, last_span_index - first_span_index + 1);
}

int SpanChain::findSpanIndex(qulonglong offset, qulonglong *span_offset) const {
    if (span_offset) {
        *span_offset = 0;
    }

    if (_spans.isEmpty() || offset >= _length) {
        return -1;
    }

    qulonglong current_offset = 0;
    for (int j = 0; j < _spans.length(); ++j) {
        if (offset >= current_offset && offset < current_offset + _spans[j]->length()) {
            if (span_offset) {
                *span_offset = offset - current_offset;
            }
            return j;
        }
        current_offset += _spans[j]->length();
    }

    return -1;
}

AbstractSpan* SpanChain::spanAtOffset(qulonglong offset, qulonglong *span_offset) const {
    int span_index = findSpanIndex(offset, span_offset);
    return span_index >= 0 ? _spans[span_index] : nullptr;
}

SpanList SpanChain::takeSpans(qulonglong offset, qulonglong length) {
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

void SpanChain::splitSpans(qulonglong offset) {
    qulonglong span_offset = 0;
    int span_index = findSpanIndex(offset, &span_offset);
    if (span_index >= 0 && span_offset) {
        auto span_to_split = _spans[span_index];
        auto splitted = span_to_split->split(span_offset);
        splitted.first->setParent(this);
        splitted.second->setParent(this);
        _spans.replace(span_index, splitted.first);
        _spans.insert(span_index + 1, splitted.second);
        delete span_to_split;
    }
}

void SpanChain::insertSpan(qulonglong offset, AbstractSpan *span) {
    insertChain(offset, SpanChain::fromSpans(SpanList() << span));
}

void SpanChain::insertChain(qulonglong offset, SpanChain *chain) {
    int span_index;
    if (offset < _length) {
        splitSpans(offset);
        span_index = findSpanIndex(offset);
    } else if (offset == _length) {
        span_index = _spans.length();
    } else {
        throw OutOfBoundsError();
    }

    SpanList spans_to_insert = _privatizeSpans(chain->spans());
    for (int j = 0; j < spans_to_insert.length(); ++j, ++span_index) {
        _spans.insert(span_index, spans_to_insert[j]);
    }
    _length += chain->length();
}

void SpanChain::remove(qulonglong offset, qulonglong length) {
    if (offset + length >= _length) {
        throw OutOfBoundsError();
    }

    auto removed_spans = takeSpans(offset, length);
    int span_index = findSpanIndex(offset);
    for (int j = 0; j < removed_spans.length(); ++j) {
        _spans.removeAt(span_index);
    }
    _length -= length;
}

void SpanChain::_dissolveSpan(AbstractSpan *span, const SpanList &replacement) {
    assert(span->length() == _calculateLength(replacement));

    SpanList privatized = _privatizeSpans(replacement);
    int span_index = _spans.indexOf(span);
    if (span_index >= 0) {
        auto replaced_span = _spans[span_index];
        _spans.replace(span_index, replacement.first());
        ++span_index;
        for (int j = 1; j < privatized.length(); ++j, ++span_index) {
            _spans.insert(span_index, privatized[j]);
        }
        delete replaced_span;
    }
}

SpanChain *SpanChain::fromSpans(const SpanList &spans) {
    SpanChain *chain(new SpanChain());
    chain->setSpans(spans);
    return chain;
}

qulonglong SpanChain::_calculateLength(const SpanList &spans) {
    qulonglong result = 0;
    for (auto span : spans) {
        result += span->length();
    }
    return result;
}

SpanList SpanChain::_privatizeSpans(const SpanList &spans) {
    SpanList result;
    for (int j = 0; j < spans.length(); ++j) {
        auto span = spans[j]->clone();
        span->setParent(this);
        result.append(span);
    }
    return result;
}

