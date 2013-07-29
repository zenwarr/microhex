#include "document.h"
#include <cassert>
#include <QDebug>
#include "chain.h"
#include "devices.h"
#include "spans.h"

int generateBranchId() {
    static int _last_branch_id = 0;
    return ++_last_branch_id;
}

class InsertAction : public AbstractUndoAction {
public:
    InsertAction(Document *document, qulonglong position, SpanChain *chain, const QString &title=QString())
        : AbstractUndoAction(document,
                             title.isEmpty() ? QString("inserting %1 bytes from position %2").arg(chain->length()).arg(position)
                                             : title)
        , _position(position), _chain(chain) {
        _chain->setParent(this);
    }

    void undo() {
        document()->_remove(_position, _chain->length(), true);
    }

    void redo() {
        document()->_insertChain(_position, _chain, 0, true);
    }

private:
    qulonglong _position;
    SpanChain *_chain;
};


class RemoveAction : public AbstractUndoAction {
public:
    RemoveAction(Document *document, qulonglong position, SpanChain *chain, const QString &title=QString())
        : AbstractUndoAction(document,
                             title.isEmpty() ? QString("removing %1 bytes from position %2").arg(chain->length()).arg(position)
                                             : title)
        , _position(position), _chain(chain) {
        _chain->setParent(this);
    }

    void undo() {
        document()->_insertChain(_position, _chain, 0, true);
    }

    void redo() {
        document()->_remove(_position, _chain->length(), true);
    }

private:
    qulonglong _position;
    SpanChain *_chain;
};


ComplexAction::ComplexAction(Document *document, const QString &title)
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

void ComplexAction::addAction(AbstractUndoAction *action) {
    action->setParent(this);
    _startNewBranch();
    _subActions.append(action);
    _currentStep = _subActions.length() - 1;
}

bool ComplexAction::canUndo()const {
    return _currentStep >= 0;
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


Document::Document(AbstractDevice *device) : _lock(new QReadWriteLock(QReadWriteLock::Recursive)),
    _spanChain(new SpanChain()), _undoDisabled(false), _fixedSize(false), _readOnly(false),
    _currentAtomicOperationIndex(), _savepoint() {

    _spanChain->setParent(this);
    _currentUndoAction = new ComplexAction(nullptr, "initial state");
    _device = device;
    if (_device) {
        _fixedSize = _device->fixedSize();
        _readOnly = _device->readOnly();

        auto device_span = new DeviceSpan(_device, 0, _device->length());
        device_span->savepoint = 0;
        _spanChain->setSpans(SpanList() << device_span);  // do not emit any signals
    }
}

Document::~Document() {
    delete _lock;
}

AbstractDevice *Document::device() const {
    return _device;
}

QUrl Document::url() const {
    return _device ? _device->url() : QUrl();
}

qulonglong Document::length() const {
    return _spanChain->length();
}

bool Document::fixedSize() const {
    return _fixedSize;
}

void Document::setFixedSize(bool fixed_size) {
    if (!fixed_size && _device && _device->fixedSize()) {
        throw DocumentError("failed to turn fixed size mode off for device with fixed size");
    }
    _fixedSize = fixed_size;
}

bool Document::readOnly() const {
    return _readOnly;
}

void Document::setReadOnly(bool read_only) {
    if (!read_only && _device && _device->readOnly()) {
        throw DocumentError("failed to turn read only mode off for read only device");
    }
    _readOnly = read_only;
}

QByteArray Document::read(qulonglong position, qulonglong length) const {
    return _spanChain->read(position, length);
}

QByteArray Document::readAll() const {
    return _spanChain->read(0, _spanChain->length());
}

void Document::insertSpan(qulonglong position, AbstractSpan *span, char fill_byte) {
    insertChain(position, SpanChain::fromSpans(SpanList() << span), fill_byte);
}

void Document::insertChain(qulonglong position, SpanChain *chain, char fill_byte) {
    {
        QWriteLocker locker(_lock);
        _insertChain(position, chain, fill_byte, false);
    }

    if (chain->length()) {
        emit resized(_spanChain->length());
        emit bytesInserted(position, chain->length());
        qulonglong change_position = std::min(_spanChain->length() - chain->length(), position);
        emit dataChanged(change_position, _spanChain->length() - change_position);
    }
}

void Document::appendSpan(AbstractSpan *span) {
    QWriteLocker locker(_lock);
    insertChain(_spanChain->length(), SpanChain::fromSpans(SpanList() << span));
}

void Document::appendChain(SpanChain *chain) {
    QWriteLocker locker(_lock);
    insertChain(_spanChain->length(), chain);
}

void Document::_insertChain(qulonglong position, SpanChain *chain, char fill_byte, bool undo) {
    QWriteLocker locker(_lock);

    if (_readOnly) {
        throw ReadOnlyError();
    } else if (_fixedSize && chain->length()) {
        throw FrozenSizeError();
    }

    if (position > _spanChain->length()) {
        auto fill_span = new FillSpan(fill_byte, position - _spanChain->length());
        _spanChain->insertChain(_spanChain->length(), SpanChain::fromSpans(SpanList() << fill_span));
        position = _spanChain->length();
    }

    _spanChain->insertChain(position, chain);

    if (!undo) {
        addAction(new InsertAction(this, position, SpanChain::fromSpans(chain->spans())));
    }

    _incrementAtomicOperationIndex(undo ? -1 : 1);
}

void Document::writeSpan(qulonglong position, AbstractSpan *span, char fill_byte) {
    writeChain(position, SpanChain::fromSpans(SpanList() << span), fill_byte);
}

void Document::writeChain(qulonglong position, SpanChain *chain, char fill_byte) {
    QWriteLocker locker(_lock);

    if (_readOnly) {
        throw ReadOnlyError();
    } else if (_fixedSize && position + chain->length() > this->length()) {
        throw FrozenSizeError();
    }

    bool filling = position > this->length();
    qulonglong old_length = this->length();

    beginComplexAction(QString("writing %1 bytes at position %2").arg(chain->length(), position));
    try {
        if (position < this->length()) {
            _remove(position, chain->length(), false);
        }
        _insertChain(position, chain, fill_byte, false);
    } catch (...) {
        endComplexAction();
    }

    if (filling) {
        emit dataChanged(old_length, this->length() - old_length);
    } else {
        emit dataChanged(position, chain->length());
    }
}

void Document::remove(qulonglong position, qulonglong length) {
    _remove(position, length, false);

    if (length) {
        emit resized(this->length());
        emit bytesRemoved(position, length);
        emit dataChanged(position, this->length() - position);
    }
}

void Document::clear() {
    remove(0, this->length());
}

bool Document::isModified() const {
    return _currentAtomicOperationIndex != _savepoint;
}

bool Document::isRangeModified(qulonglong position, qulonglong length) const {
    if (!isModified() || position >= this->length()) {
        return false;
    } else if (position + length > this->length()) {
        length = this->length() - position;
    }
    SpanList spans_to_check = _spanChain->spansInRange(position, length);
    for (int j = 0; j < spans_to_check.length(); ++j) {
        if (spans_to_check[j]->savepoint != _savepoint) {
            return true;
        }
    }
    return false;
}

void Document::_remove(qulonglong position, qulonglong length, bool undo) {
    if (_readOnly) {
        throw ReadOnlyError();
    } else if (_fixedSize && length) {
        throw FrozenSizeError();
    }

    if (position >= this->length()) {
        return;
    } else if (position + length > this->length()) {
        length = this->length() - position;
    }

    SpanChain removed_spans(_spanChain->takeSpans(position, length));
    _spanChain->remove(position, length);

    if (!undo) {
        addAction(new RemoveAction(this, position, new SpanChain(removed_spans.spans())));
    }

    _incrementAtomicOperationIndex(undo ? -1 : 1);
}

void Document::_incrementAtomicOperationIndex(int inc) {
    bool was_modified = isModified();
    _currentAtomicOperationIndex += inc;
    if (was_modified != isModified()) {
        emit isModifiedChanged(isModified());
    }
}

void Document::undo() {
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

void Document::addAction(AbstractUndoAction *action) {
    _currentUndoAction->addAction(action);
}

void Document::beginComplexAction(const QString &title) {
    _currentUndoAction->addAction(new ComplexAction(this, title));
}

void Document::endComplexAction() {
    if (!_currentUndoAction->parentAction()) {
        throw DocumentError("trying to end complex action while there are no open actions");
    }
    _currentUndoAction = _currentUndoAction->parentAction();
}

bool Document::canUndo()const {
    return _currentUndoAction->canUndo();
}

bool Document::canRedo()const {
    return _currentUndoAction->canRedo();
}

QList<int> Document::alternativeBranchesIds()const {
    return _currentUndoAction->alternativeBranchesIds();
}

void Document::save(AbstractDevice *write_device, bool switch_devices) {
    auto device_to_write = write_device ? write_device : _device;
    auto device_to_read = _device;

    if (device_to_write == _device && !isModified()) {
        return;
    }

    if (!device_to_read || !device_to_write) {
        throw DocumentError();
    }

    auto saver = device_to_write->createSaver(this, device_to_read);

    if (device_to_read == device_to_write || switch_devices) {
        _prepareToUpdateDevice(switch_devices ? device_to_write : device_to_read);
    }

    saver->begin();
    try {
        SpanList spans = _spanChain->spans();
        for (auto span : spans) {
            saver->putSpan(span);
        }
    } catch (...) {
        saver->fail();
        for (auto span : _device->spans()) {
            span->cancelDissolve();
        }
        throw;
    }

    saver->complete();

    if (switch_devices) {
        _device = device_to_write;
    }

//    if (device_to_read == device_to_write || switch_devices) {
//        qulonglong current_position = 0;
//        for (int j = 0; j < _spanChain->length(); ++j) {
//            auto deviceSpan = std::dynamic_pointer_cast<DeviceSpan>(_spanChain->spans()[j]);
//            if (deviceSpan) {
//                deviceSpan->adjust(_device, current_position);
//            }
//            current_position += _spanChain->spans()[j]->length();
//        }

//        auto device_spans = device_to_write->spans();
//        for (auto span_weak : device_spans) {
//            auto span = span_weak.lock();
//            if (span) {
//                span->dissolve();
//            }
//        }
//    }

    _setSavepoint();

    if (switch_devices) {
        emit urlChanged(this->url());
    }
}

bool Document::checkCanQuickSave() const {
    qulonglong current_position = 0;
    for (auto span : _spanChain->spans()) {
        auto device_span = dynamic_cast<DeviceSpan*>(span);
        if (device_span && device_span->deviceOffset() != current_position) {
            return false;
        }
        current_position += span->length();
    }
    return true;
}

void Document::_setSavepoint() {
    if (_savepoint != _currentAtomicOperationIndex) {
        _savepoint = _currentAtomicOperationIndex;
        for (int j = 0; j < _spanChain->spans().length(); ++j) {
            _spanChain->spans()[j]->savepoint = _savepoint;
        }
        emit isModifiedChanged(this->isModified());
    }
}

void Document::_prepareToUpdateDevice(AbstractDevice *new_device) {
    // build list of spans that represent data blocks from original device remaining in saved device
//    QList< std::shared_ptr<DeviceSpan> > alive_spans;
//    for (int j = 0; j < _spanChain->spans().length(); ++j) {
//        auto device_span = qSharedPointerDynamicCast<DeviceSpan>(_spanChain->spans()[j]);
//        if (device_span && device_span->device() == _device) {
//            alive_spans.append(device_span);
//        }
//    }

//    // build list of spans we should dissolve. This is spans that are not in main chain.
//    QList< std::shared_ptr<DeviceSpan> > spans_to_dissolve;
//    auto all_device_spans = _device->spans();
//    for (int j = 0; j < all_device_spans.length(); ++j) {
//        if (all_device_spans[j]->parentChain() != _spanChain) {
//            spans_to_dissolve.append(all_device_spans[j]);
//        }
//    }

//    // iterate over spans to dissolve and find out how we can replace its contents
//    for (int j = 0; j < spans_to_dissolve.length(); ++j) {
//        QList< AbstractSpan* > replacement;
//        auto span_to_dissolve = spans_to_dissolve[j];
//        qulonglong dev_position = spans_to_dissolve->deviceOffset();
//        while (dev_position < span_to_dissolve->deviceOffset() + span_to_dissolve->length()) {
//            // find
//        }
}



AbstractUndoAction::AbstractUndoAction(Document *document, const QString &title)
    : _document(document), _title(title) {

}

AbstractUndoAction::~AbstractUndoAction() {

}

Document *AbstractUndoAction::document() {
    return _document;
}

QString AbstractUndoAction::title()const {
    return _title;
}

ComplexAction *AbstractUndoAction::parentAction() const {
    return dynamic_cast<ComplexAction*>(parent());
}

