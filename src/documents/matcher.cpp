#include "matcher.h"
#include "document.h"

int MATCHER_BUFFER_SIZE = 1024 * 1024;

BinaryFinder::BinaryFinder(const std::shared_ptr<Document> &doc, const QByteArray &findWhat)
    : _document(doc), _findWhat(findWhat) {
    // build offset table
    _offsetTable = QByteArray(256, findWhat.length());
    for (int j = 0; j < findWhat.length(); ++j) {
        _offsetTable[(unsigned char)findWhat[j]] = findWhat.length() - j;
    }

    // build reversed offset table
    _reversedOffsetTable = QByteArray(256, findWhat.length());
    for (int j = findWhat.length() - 1; j >= 0; --j) {
        _reversedOffsetTable[(unsigned char)findWhat[j]] = j + 1;
    }
}

qulonglong BinaryFinder::findNext(qulonglong position, qulonglong limit, bool *found) {
    ReadLocker locker(_document->getLock());

    if (found) {
        *found = false;
    }

    if (_document->getLength() - position < qulonglong(_findWhat.length()) || _findWhat.isEmpty()) {
        return 0;
    }

    QByteArray buffer = _document->read(position, MATCHER_BUFFER_SIZE);
    qulonglong buffer_start = position;

    qulonglong pattern_end_position = position + _findWhat.length() - 1;
    while (pattern_end_position < _document->getLength()) {
        if (pattern_end_position >= buffer_start + buffer.length()) {
            // shift buffer
            buffer_start = pattern_end_position - _findWhat.length();
            buffer = _document->read(buffer_start, MATCHER_BUFFER_SIZE);
        }

        for (int pattern_index = 0; pattern_index < _findWhat.length(); ++pattern_index) {
            unsigned char current_byte = (unsigned char)(buffer[int(pattern_end_position - buffer_start - pattern_index)]);
            if (current_byte != (unsigned char)(_findWhat[_findWhat.length() - pattern_index - 1])) {
                pattern_end_position += _offsetTable[(unsigned char)(buffer[int(pattern_end_position - buffer_start)])];
                break;
            } else if (pattern_index == _findWhat.length() - 1) {
                // we have found it!
                if (found) {
                    *found = true;
                }
                return pattern_end_position - _findWhat.length() + 1;
            }
        }

        if (pattern_end_position - position >= limit) {
            return 0;
        }
    }
    return 0;
}

qulonglong BinaryFinder::findPrevious(qulonglong position, qulonglong limit, bool *found) {
    ReadLocker locker(_document->getLock());

    if (found) {
        *found = false;
    }

    if (position < qulonglong(_findWhat.length()) || _findWhat.isEmpty()) {
        return 0;
    }

    QByteArray buffer;
    qulonglong buffer_start;
    if (position < qulonglong(MATCHER_BUFFER_SIZE)) {
        buffer = _document->read(0, position);
        buffer_start = 0;
    } else {
        buffer_start = position - MATCHER_BUFFER_SIZE;
        buffer = _document->read(buffer_start, MATCHER_BUFFER_SIZE);
    }

    qulonglong pattern_start_position = position - _findWhat.length();
    while (true) {
        if (pattern_start_position < buffer_start) {
            qulonglong buffer_end = pattern_start_position + _findWhat.length();
            if (buffer_end < qulonglong(MATCHER_BUFFER_SIZE)) {
                buffer = _document->read(0, buffer_end);
                buffer_start = 0;
            } else {
                buffer_start = buffer_end - MATCHER_BUFFER_SIZE;
                buffer = _document->read(buffer_start, MATCHER_BUFFER_SIZE);
            }
        }

        for (int pattern_index = 0; pattern_index < _findWhat.length(); ++pattern_index) {
            unsigned char current_byte = (unsigned char)(buffer[int(pattern_start_position - buffer_start + pattern_index)]);
            if (current_byte != (unsigned char)_findWhat[pattern_index]) {
                // shift pattern
                unsigned char shift = _reversedOffsetTable[(unsigned char)(buffer[int(pattern_start_position - buffer_start)])];
                if (pattern_start_position < qulonglong(shift)) {
                    return 0;
                } else {
                    pattern_start_position -= shift;
                    break;
                }
            } else if (pattern_index == _findWhat.length() - 1) {
                // match
                if (found) {
                    *found = true;
                }
                return pattern_start_position;
            }
        }

        if (position - pattern_start_position >= limit) {
            return 0;
        }
    }

    return 0;
}
