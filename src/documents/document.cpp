#include "document.h"
#include "chain.h"
#include "devices.h"
#include "spans.h"
#include <memory>

int generateBranchId() {
    static int _last_branch_id = 0;
    return ++_last_branch_id;
}

class InsertAction : public AbstractUndoAction {
public:
    InsertAction(const std::shared_ptr<Document> &document, qulonglong position,
                 const std::shared_ptr<SpanChain> &chain, const QString &title=QString())
        : AbstractUndoAction(document,
                             title.isEmpty() ? QString("inserting %1 bytes from position %2").arg(chain->getLength()).arg(position)
                                             : title)
        , _position(position), _chain(chain) {

    }

    void undo() {
        auto doc = getDocument();
        if (doc) {
            doc->_remove(_position, _chain->getLength(), true, -1);
        }
    }

    void redo() {
        auto doc = getDocument();
        if (doc) {
            doc->_insertChain(_position, _chain, 0, true, 1);
        }
    }

private:
    qulonglong _position;
    const std::shared_ptr<SpanChain> _chain;
};


class RemoveAction : public AbstractUndoAction {
public:
    RemoveAction(const std::shared_ptr<Document> &document, qulonglong position,
                 const std::shared_ptr<SpanChain> &chain, const QString &title=QString())
        : AbstractUndoAction(document,
                             title.isEmpty() ? QString("removing %1 bytes from position %2").arg(chain->getLength()).arg(position)
                                             : title)
        , _position(position), _chain(chain) {

    }

    void undo() {
        auto doc = getDocument();
        if (doc) {
            doc->_insertChain(_position, _chain, 0, true, -1);
        }
    }

    void redo() {
        auto doc = getDocument();
        if (doc) {
            doc->_remove(_position, _chain->getLength(), true, 1);
        }
    }

private:
    qulonglong _position;
    std::shared_ptr<SpanChain> _chain;
};


class WriteAction : public AbstractUndoAction {
public:
    WriteAction(const std::shared_ptr<Document> &document, qulonglong position,
                const std::shared_ptr<SpanChain> &overwritten_chain, const std::shared_ptr<SpanChain> &written_chain,
                const QString &title=QString())
        : AbstractUndoAction(document,
                             title.isEmpty() ? QString("writing %1 bytes at position %2").arg(written_chain->getLength()).arg(position)
                                              : title)
        , _position(position), _overwrittenChain(overwritten_chain), _writtenChain(written_chain) {

    }

    void undo() {
        _do(true);
    }

    void redo() {
        _do(false);
    }

private:
    qulonglong _position;
    std::shared_ptr<SpanChain> _overwrittenChain, _writtenChain;

    void _do(bool undo) {
        auto doc = getDocument();
        if (!doc) {
            return;
        }
        int done_increment = _overwrittenChain->getLength() ? (undo ? -1 : 1) : 0;
        doc->_writeChain(_position, _overwrittenChain, 0, true, done_increment);
        if (_overwrittenChain->getLength() < _writtenChain->getLength()) {
            done_increment = done_increment ? 0 : (undo ? -1 : 1);
            doc->_remove(_position + _overwrittenChain->getLength(),
                                   _writtenChain->getLength() - _overwrittenChain->getLength(), true, done_increment);
        }

        std::swap(_overwrittenChain, _writtenChain);
    }
};


ComplexAction::ComplexAction(const std::shared_ptr<Document> &document, const QString &title)
    : AbstractUndoAction(document, title), _currentStep(-1) {

}

void ComplexAction::undoStep() {
    // call to this method will undo subaction with _currentIndex
    if (_currentStep >= 0) {
        _subActions[_currentStep]->undo();
        --_currentStep;
    }
}

void ComplexAction::redoStep(int branch_id) {
    // call to this method will redo subaction with _currentIndex + 1
    if (_currentStep + 1 <= _subActions.length()) {
        if (branch_id >= 0) {
            Branch alternate;
            int found_branch_index = -1;

            // try to switch to another branch: find one that starts at current index
            int j = 0;
            for (auto branch : _branches) {
                if (branch.startIndex == _currentStep + 1 && branch.id == branch_id) {
                    alternate = branch;
                    found_branch_index = j;
                    break;
                }
                ++j;
            }

            if (alternate.id < 0) {
                throw DocumentError("failed to switch to another redo branch: no such branch after current");
            }

            // remove choosen branch from list
            _branches.removeAt(found_branch_index);

            _startNewBranch();
            _subActions.append(alternate.actions);
        }

        _subActions[_currentStep + 1]->redo();
        ++_currentStep;
    }
}

void ComplexAction::_startNewBranch() {
    // stores current undo branch starting from _currentIndex +1 in alternating branches list
    if (_currentStep + 1 != _subActions.length()) {
        Branch branch_to_back;
        branch_to_back.actions = _subActions.mid(_currentStep + 1);
        branch_to_back.id = generateBranchId();
        branch_to_back.startIndex = _currentStep + 1;

        _subActions.erase(_subActions.begin() + _currentStep + 1, _subActions.end());
    }
}

void ComplexAction::undo() {
    while (canUndo()) {
        undoStep();
    }
}

void ComplexAction::redo() {
    while (canRedo()) {
        redoStep();
    }
}

void ComplexAction::addAction(const std::shared_ptr<AbstractUndoAction> &action) {
    action->setParentAction(std::dynamic_pointer_cast<ComplexAction>(shared_from_this()));
    _startNewBranch();
    _subActions.append(action);
    _currentStep = _subActions.length() - 1;
}

bool ComplexAction::canUndo()const {
    return _currentStep >= 0 && !_subActions.isEmpty();
}

bool ComplexAction::canRedo()const {
    return _currentStep + 1 != _subActions.length();
}

QList<int> ComplexAction::alternativeBranchesIds()const {
    QList<int> result;
    for (int j = 0; j < _branches.length(); ++j) {
        result.append(_branches[j].id);
    }
    return result;
}

/*
 * Document class provides high-level functions for editing data.
 */
Document::Document(const std::shared_ptr<AbstractDevice> &device) : _spanChain(std::make_shared<SpanChain>()),
    _currentUndoAction(std::make_shared<ComplexAction>(std::shared_ptr<Document>(), "initial state")),
    _undoDisabled(false), _fixedSize(false), _readOnly(false), _currentAtomicOperationIndex(),
    _savepoint(), _lock(std::make_shared<ReadWriteLock>()) {

    _rootAction = _currentUndoAction;
    _device = device;
    if (_device) {
        ReadLocker dlocker(_device->getLock());

        _fixedSize = _device->isFixedSize();
        _readOnly = _device->isReadOnly();

        if (device->getLength()) {
            auto span = device->createSpan(0, _device->getLength());
            _spanChain->setSpans(SpanList() << span);
            _spanChain->setCommonSavepoint(0);
        }

        connect(_device.get(), SIGNAL(readOnlyChanged(bool)), this, SLOT(_onDeviceReadOnlyChanged(bool)));
    }
}

Document::Document(const std::shared_ptr<SpanChain> &chain) : Document(std::shared_ptr<AbstractDevice>()) {
    _spanChain = chain;
}

Document::~Document() {

}

const std::shared_ptr<AbstractDevice> &Document::getDevice() const {
    return _device;
}

/*
 * Note that device URL is not unique for device. For example, all BufferDevices share exactly
 * same URL (microdata://)
 */
QUrl Document::getUrl() const {
    ReadLocker locker(_lock);
    return _device ? _device->getUrl() : QUrl();
}

qulonglong Document::getLength() const {
    ReadLocker locker(_lock);
    return _spanChain->getLength();
}

bool Document::isFixedSize() const {
    return _fixedSize;
}

/*
 * Turns fixed size mode on and off. In fixed size mode all operations leading to changing
 * size of data will fail. Fixed size mode can only be changed if device->isFixedSize() is false.
 * Otherwise fixed size mode of document is always true.
 */
void Document::setFixedSize(bool fixed_size) {
    WriteLocker locker(_lock);
    if (fixed_size != _fixedSize) {
        if (!fixed_size && _device && _device->isFixedSize()) {
            throw DocumentError("cannot turn fixed size mode off for device with fixed size");
        }
        _fixedSize = fixed_size;
        emit fixedSizeChanged(fixed_size);
    }
}

bool Document::isReadOnly() const {
    ReadLocker locker(_lock);
    return _readOnly;
}

/*
 * Turns read only mode on and off. In read only mode all operations leading to changing
 * data will fail. Read only mode can only be changed if device->isReadOnly() is false.
 * Otherwise read only mode of document is always true.
 */
void Document::setReadOnly(bool read_only) {
    WriteLocker locker(_lock);
    if (read_only != _readOnly) {
        if (!read_only && _device && _device->isReadOnly()) {
            throw DocumentError("cannot turn read only mode off for read only device");
        }
        _readOnly = read_only;
        emit readOnlyChanged(read_only);
    }
}

/*
 * Reads :length: bytes starting from :position:. If no :length: bytes available, it will return
 * as many bytes as possible.
 */
QByteArray Document::read(qulonglong position, qulonglong length) const {
    ReadLocker locker(_lock);
    return _spanChain->read(position, length);
}

/*
 * Reads all available data from document.
 */
QByteArray Document::readAll() const {
    ReadLocker locker(_lock);
    return _spanChain->read(0, _spanChain->getLength());
}

/*
 * Inserts span at given position. See Document::insertChain doc for details.
 */
void Document::insertSpan(qulonglong position, const std::shared_ptr<AbstractSpan> &span, char fill_byte) {
    insertChain(position, SpanChain::fromSpans(SpanList() << span), fill_byte);
}

/*
 * Inserts given chain at :position:, shifting all data after :position: right. It is possible to
 * insert data even if position > this->getLength(), in this case space between current end of document
 * and insert position will be occupied by FillSpan initialized with :fill_byte:.
 * Given chain is cloned, so it is safe to modify :chain: after passing as argument to this function.
 */
void Document::insertChain(qulonglong position, const std::shared_ptr<SpanChain> &chain, char fill_byte) {
    _insertChain(position, chain, fill_byte, false, 1);
}

/*
 * Appends span to the end of document. See Document::appendChain for details.
 */
void Document::appendSpan(const std::shared_ptr<AbstractSpan> &span) {
    WriteLocker locker(_lock);
    insertChain(_spanChain->getLength(), SpanChain::fromSpans(SpanList() << span));
}

/*
 * Appends given chain to the end of document. Given chain is cloned, so it is safe to modify
 * :chain: after passing as argument to this function.
 */
void Document::appendChain(const std::shared_ptr<SpanChain> &chain) {
    WriteLocker locker(_lock);
    insertChain(_spanChain->getLength(), chain);
}

void Document::_insertChain(qulonglong position, const std::shared_ptr<SpanChain> &chain,
                            char fill_byte, bool from_undo, int op_increment) {
    WriteLocker locker(_lock);

    // check if we can do this operation
    if (_readOnly) {
        throw ReadOnlyError();
    } else if (_fixedSize && chain->getLength()) {
        throw FrozenSizeError();
    } else if (this->getLength() + chain->getLength() < this->getLength()) {
        throw std::overflow_error("integer overflow");
    }

    if (!chain->getLength()) {
        return;
    }

    // this chain will be inserted into document chain (and stored in undo stack too).
    auto chain_to_insert = SpanChain::fromChain(*chain);

    // should we insert chain after current document end?
    if (position > _spanChain->getLength()) {
        // in this case, prepend span to be inserted with FillSpan and adjust insert position.
        chain_to_insert->insertSpan(0, std::make_shared<FillSpan>(position - _spanChain->getLength(), fill_byte));
        position = _spanChain->getLength();
    }

    _incrementAtomicOperationIndex(op_increment);
    if (!from_undo) {
        chain_to_insert->setCommonSavepoint(_currentAtomicOperationIndex);
    }

    _spanChain->insertChain(position, chain_to_insert);

    if (!from_undo) {
        addAction(std::make_shared<InsertAction>(shared_from_this(), position, chain_to_insert));
    }

    emit resized(_spanChain->getLength());
    emit bytesInserted(position, chain_to_insert->getLength());
    emit dataChanged(position, _spanChain->getLength() - position);
}

void Document::writeSpan(qulonglong position, const std::shared_ptr<AbstractSpan> &span, char fill_byte) {
    writeChain(position, SpanChain::fromSpans(SpanList() << span), fill_byte);
}

/*
 * Writes given chain at :position:, overwriting existing data. Document will be expanded if required.
 * Space between write position and end of document will be occupied by FillSpan initialized by :fill_byte:.
 * Given chain is cloned, so it is safe to modify :chain: after passing as argument to this function.
 */
void Document::writeChain(qulonglong position, const std::shared_ptr<SpanChain> &chain, char fill_byte) {
    _writeChain(position, chain, fill_byte, false, 1);
}

void Document::_writeChain(qulonglong position, const std::shared_ptr<SpanChain> &chain,
                           char fill_byte, bool from_undo, int op_increment) {
    WriteLocker locker(_lock);

    if (_readOnly) {
        throw ReadOnlyError();
    } else if (_fixedSize && position + chain->getLength() > this->getLength()) {
        throw FrozenSizeError();
    } else if (position + chain->getLength() < position) {
        throw std::overflow_error("integer overflow");
    }

    if (!chain->getLength()) {
        return;
    }

    auto chain_to_write = SpanChain::fromChain(*chain); // also will be stored in undo stack
    std::shared_ptr<SpanChain> overwritten;

    // now we will remove data which should be overwritten
    if (position < getLength()) {
        // note that length of data we should overwrite can be less than length of data we want to write
        qulonglong remove_length = std::min(getLength() - position, chain->getLength());
        overwritten  =_spanChain->takeChain(position, remove_length);
        _spanChain->remove(position, remove_length);
    } else if (position > getLength()) {
        chain_to_write->insertSpan(0, std::make_shared<FillSpan>(position - getLength(), fill_byte));
        position = _spanChain->getLength();
    }

    _incrementAtomicOperationIndex(op_increment);

    if (!from_undo) {
        chain_to_write->setCommonSavepoint(_currentAtomicOperationIndex);
    }

    _spanChain->insertChain(position, chain_to_write);

    if (!overwritten.get()) {
        overwritten = SpanChain::fromSpans(SpanList());
    }

    if (!from_undo) {
        addAction(std::make_shared<WriteAction>(shared_from_this(), position, overwritten, chain_to_write));
    }

    if (overwritten->getLength() < chain_to_write->getLength()) {
        emit resized(getLength());
    }
    emit dataChanged(position, chain_to_write->getLength());
}

void Document::remove(qulonglong position, qulonglong length) {
    _remove(position, length, false, 1);
}

void Document::clear() {
    WriteLocker locker(_lock);
    remove(0, getLength());
}

bool Document::isModified() const {
    ReadLocker locker(_lock);
    return _currentAtomicOperationIndex != _savepoint;
}

bool Document::isRangeModified(qulonglong position, qulonglong length) const {
    ReadLocker locker(_lock);

    if (!isModified() || position >= this->getLength()) {
        return false;
    } else if (this->getLength() - length < position) {
        length = this->getLength() - position;
    }

    SpanList spans_to_check = _spanChain->spansInRange(position, length);
    for (int j = 0; j < spans_to_check.length(); ++j) {
        if (_spanChain->spanSavepoint(spans_to_check.at(j)) != _savepoint) {
            return true;
        }
    }
    return false;
}

void Document::_remove(qulonglong position, qulonglong length, bool from_undo, int op_increment) {
    if (_readOnly) {
        throw ReadOnlyError();
    } else if (_fixedSize && length) {
        throw FrozenSizeError();
    }

    if (!length) {
        return;
    }

    if (position >= this->getLength()) {
        return;
    } else if (this->getLength() - length < position) {
        length = this->getLength() - position;
    }

    auto removed = _spanChain->takeChain(position, length);

    _incrementAtomicOperationIndex(op_increment);
    _spanChain->remove(position, length);

    if (!from_undo) {
        addAction(std::make_shared<RemoveAction>(shared_from_this(), position, removed));
    }

    if (length) {
        emit resized(this->getLength());
        emit bytesRemoved(position, length);
        emit dataChanged(position, getLength() - position);
    }
}

void Document::_incrementAtomicOperationIndex(int inc) {
    if (inc) {
        bool was_modified = isModified();
        _currentAtomicOperationIndex += inc;
        if (was_modified != isModified()) {
            emit isModifiedChanged(isModified());
        }
    }
}

void Document::undo() {
    WriteLocker locker(_lock);
    if (canUndo()) {
        bool old_can_undo  = canUndo(), old_can_redo = canRedo();
        _currentUndoAction->undoStep();
        if (old_can_undo != canUndo()) {
            emit canUndoChanged(canUndo());
        }
        if (old_can_redo != canRedo()) {
            emit canRedoChanged(canRedo());
        }
    }
}

void Document::redo(int branch_id) {
    WriteLocker locker(_lock);
    if (canRedo()) {
        bool old_can_undo  = canUndo(), old_can_redo = canRedo();
        _currentUndoAction->redoStep(branch_id);
        if (old_can_undo != canUndo()) {
            emit canUndoChanged(canUndo());
        }
        if (old_can_redo != canRedo()) {
            emit canRedoChanged(canRedo());
        }
    }
}

void Document::addAction(const std::shared_ptr<AbstractUndoAction> &action) {
    WriteLocker locker(_lock);
    bool old_can_undo = canUndo();
    _currentUndoAction->addAction(action);
    if (old_can_undo != canUndo()) {
        emit canUndoChanged(canUndo());
    }
}

void Document::beginComplexAction(const QString &title) {
    WriteLocker locker(_lock);
    auto new_sub_action = std::make_shared<ComplexAction>(shared_from_this(), title);
    _currentUndoAction->addAction(new_sub_action);
    _currentUndoAction = new_sub_action;
}

void Document::endComplexAction() {
    WriteLocker locker(_lock);
    if (!_currentUndoAction->getParentAction()) {
        throw DocumentError("trying to end complex action while there are no open actions");
    }
    _currentUndoAction = _currentUndoAction->getParentAction();
}

bool Document::canUndo()const {
    ReadLocker locker(_lock);
    return _currentUndoAction->canUndo();
}

bool Document::canRedo()const {
    ReadLocker locker(_lock);
    return _currentUndoAction->canRedo();
}

QList<int> Document::getAlternativeBranchesIds()const {
    ReadLocker locker(_lock);
    return _currentUndoAction->alternativeBranchesIds();
}

/*
 * Saves data to specified device. If no device was specified, underlying device will be used.
 */
void Document::save(const std::shared_ptr<AbstractDevice> &write_device, bool switch_devices) {
    WriteLocker locker(_lock);

    auto device_to_write = write_device ? write_device : _device;
    auto device_to_read = _device;

    if (!device_to_write) {
        throw DocumentError();
    }

    // save to underlying device only if document was modified
    if (device_to_write == _device && !isModified()) {
        return;
    }

    // Saver object encapsulates algorithm of writing data to device. For example, FileDevice
    // can create QuickFileSaver object which will overwrite only modified bytes.
    auto saver = device_to_write->createSaver(shared_from_this(), device_to_read);

    // build list of DeviceSpan that should be dissolved
    QList<std::shared_ptr<PrimitiveDeviceSpan>> spans_to_dissolve;
    spans_to_dissolve = _prepareToUpdateDevice(device_to_write);

    saver->begin();
    try {
        SpanList spans = _spanChain->getSpans();
        for (auto span : spans) {
            span->put(saver);
        }
    } catch (...) {
        saver->fail();
        for (auto span : _device->getSpans()) {
            span->cancelDissolve();
        }
        throw;
    }

    saver->complete();

    if (switch_devices) {
        _device = device_to_write;
    }

    if (device_to_read == device_to_write || switch_devices) {
        // replace all this with one device span...
        if (getLength()) {
            _spanChain->setSpans(SpanList() << std::make_shared<DeviceSpan>(_device, 0, _device->getLength()));
        }
    }

    for (auto span : spans_to_dissolve) {
        try {
            span->dissolve();
        } catch (...) {
            // do nothing
        }
    }

    _setSavepoint();

    if (switch_devices) {
        emit urlChanged(this->getUrl());
    }
}

bool Document::checkCanQuickSave() const {
    ReadLocker locker(_lock);

    qulonglong current_position = 0;
    for (auto span : _spanChain->getSpans()) {
        auto device_span = std::dynamic_pointer_cast<DeviceSpan>(span);
        if (device_span) {
            auto map = device_span->getPrimitives();
            for (auto primitive_span : map.keys()) {
                if (primitive_span->getDevice() == getDevice() &&
                        primitive_span->getDeviceOffset() != current_position + map[primitive_span]) {
                    return false;
                }
            }
        }
        current_position += span->getLength();
    }
    return true;
}

const std::shared_ptr<SpanChain> Document::exportRange(qulonglong position, qulonglong length, int ram_limit) const {
    return _spanChain->exportRange(position, length, ram_limit);
}

std::shared_ptr<Document> Document::createConstantFrame(qulonglong start, qulonglong length) {
    std::shared_ptr<Document> frame_doc(new Document(_spanChain->exportRange(start, length, 0)));
    frame_doc->setReadOnly(true);
    return frame_doc;
}

void Document::_setSavepoint() {
    if (_savepoint != _currentAtomicOperationIndex) {
        _savepoint = _currentAtomicOperationIndex;
        _spanChain->setCommonSavepoint(_savepoint);
        emit isModifiedChanged(this->isModified());
    }
}

void Document::_onDeviceReadOnlyChanged(bool new_read_only) {
    if (new_read_only && !isReadOnly()) {
        _readOnly = new_read_only;
        emit readOnlyChanged(new_read_only);
    }
}

struct SAVED_RANGE {
    qulonglong oldPos;
    qulonglong newPos;
    qulonglong length = 0;
};

QList<std::shared_ptr<PrimitiveDeviceSpan> > Document::_prepareToUpdateDevice(
        const std::shared_ptr<AbstractDevice> &write_device) {
    // Saved range (SR) is range of device data that exist in device both before and after saving
    // operation (although its offset from beginning of device can differ).

    // collect list of SRs
    QList<SAVED_RANGE> saved_ranges;
    qulonglong current_position = 0;
    for (auto span : _spanChain->getSpans()) {
        auto device_span = std::dynamic_pointer_cast<DeviceSpan>(span);
        if (device_span) {
            auto map = device_span->getPrimitives();
            for (auto primitive_span : map.keys()) {
                if (primitive_span->getDevice() == write_device) {
                    SAVED_RANGE sr;
                    sr.length = primitive_span->getLength();
                    sr.oldPos = primitive_span->getDeviceOffset();
                    sr.newPos = current_position + map[primitive_span];
                    saved_ranges.push_back(sr);
                }
            }
        }
        current_position += span->getLength();
    }

    // iterate over list of all PrimitiveDeviceSpans referencing :write_device: data and
    // determine replacement for each one
    QList<std::shared_ptr<PrimitiveDeviceSpan>> spans_to_dissolve;
    for (auto span : write_device->getSpans()) {
        SpanList replacement;

        qulonglong cur_device_pos = span->getDeviceOffset();
        while (cur_device_pos < span->getDeviceOffset() + span->getLength()) {
            // collect list of SRs this byte hits.
            QList<SAVED_RANGE> hitted_srs;
            for (auto sr : saved_ranges) {
                if (sr.oldPos <= cur_device_pos && cur_device_pos < sr.oldPos + sr.length) {
                    hitted_srs.append(sr);
                }
            }

            if (hitted_srs.isEmpty()) {
                // there is no SRs containing this byte. It means that this
                // data will not be present in device after saving, but we still need it. We should
                // back removed device data in DataSpan.
                // Now we determine how many bytes we should store. First find closest SR to the
                // right of current byte.
                SAVED_RANGE closest;
                qulonglong closest_dist = std::numeric_limits<qulonglong>::max();
                for (auto sr : saved_ranges) {
                    if (sr.oldPos > cur_device_pos && (!closest.length || sr.oldPos - cur_device_pos < closest_dist)) {
                        closest = sr;
                        closest_dist = sr.oldPos - cur_device_pos;
                    }
                }

                qulonglong data_to_store_length;
                if (!closest.length) {
                    // there is no another SRs till the end of device... We should store all remaining data
                    data_to_store_length = span->getLength() - (cur_device_pos - span->getDeviceOffset());
                } else {
                    // another SR is near...
                    data_to_store_length = closest.oldPos - cur_device_pos;
                }
                data_to_store_length = std::min(span->getDeviceOffset() + span->getLength() - cur_device_pos,
                                                data_to_store_length);

                // now replace with data span. Problem is that we can have no enough memory to keep
                // all data in memory, so we should ask user to do something (we can't say what exactly)
                // to remove this span - clear undo history, save another document that depends on this device
                // data, etc.
                bool ok = false;
                QByteArray data_to_store;
                try {
                    data_to_store = write_device->read(cur_device_pos, data_to_store_length);
                    ok = true;
                } catch (const std::bad_alloc &) {
                    // not enough memory
                    ok = false;
                }

                if (!ok || qulonglong(data_to_store.length()) != data_to_store_length) {
                    throw DocumentError("failed to save document data - some data from device you want to write into "
                                        "should be kept, but system has no enough free RAM to do it, or data is "
                                        "unavailable. Try clearing "
                                        "undo history, or save another document that depends on data from this device.");
                }

                replacement.append(std::make_shared<DataSpan>(data_to_store));
            } else {
                // part of data hits SR. Find out how many bytes we have
                //TODO: iterate over SRs and choose longest one!
                SAVED_RANGE choosen = hitted_srs.first();
                qulonglong offset = cur_device_pos - choosen.oldPos;
                qulonglong length = std::min(span->getDeviceOffset() + span->getLength() - cur_device_pos,
                                             choosen.length - offset);

                replacement.append(write_device->createSpan(choosen.newPos + offset, length));
            }
            cur_device_pos += replacement.last()->getLength();
        }
        span->prepareToDissolve(replacement);
        spans_to_dissolve.append(span);
    }

    return spans_to_dissolve;
}


AbstractUndoAction::AbstractUndoAction(const std::shared_ptr<Document> &document, const QString &title)
    : _document(document), _title(title) {

}

AbstractUndoAction::~AbstractUndoAction() {

}

std::shared_ptr<Document> AbstractUndoAction::getDocument() {
    return _document.lock();
}

QString AbstractUndoAction::getTitle()const {
    return _title;
}

std::shared_ptr<ComplexAction> AbstractUndoAction::getParentAction() const {
    return _parentAction.lock();
}

void AbstractUndoAction::setParentAction(const std::shared_ptr<ComplexAction> &action) {
    _parentAction = action;
}
