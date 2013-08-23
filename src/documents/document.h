#ifndef DOCUMENT_H
#define DOCUMENT_H

#include <exception>
#include <memory>
#include <QObject>
#include <QUrl>
#include <QByteArray>
#include "readwritelock.h"
#include "base.h"


class SpanChain;
class AbstractUndoAction;
class AbstractSpan;
class ComplexAction;
class AbstractDevice;
class PrimitiveDeviceSpan;


class DocumentError : public BaseException {
public:
    DocumentError(const QString &desc=QString()) : BaseException(desc) { }
};


class Document : public QObject, public std::enable_shared_from_this<Document> {
    Q_OBJECT
    friend class InsertAction;
    friend class RemoveAction;
    friend class WriteAction;
public:
    Document(const std::shared_ptr<AbstractDevice> &device=std::shared_ptr<AbstractDevice>());
    ~Document();

    std::shared_ptr<ReadWriteLock> getLock() { return _lock; }

    const std::shared_ptr<AbstractDevice> &getDevice()const;
    QUrl getUrl()const;
    qulonglong getLength()const;
    bool isFixedSize()const;
    void setFixedSize(bool fixed_size);
    bool isReadOnly()const;
    void setReadOnly(bool read_only);

    QByteArray read(qulonglong position, qulonglong length)const;
    QByteArray readAll()const;

    void insertSpan(qulonglong position, const std::shared_ptr<AbstractSpan> &span, char fill_byte=0);
    void insertChain(qulonglong position, const std::shared_ptr<SpanChain> &chain, char fill_byte=0);
    void appendSpan(const std::shared_ptr<AbstractSpan> &span);
    void appendChain(const std::shared_ptr<SpanChain> &chain);
    void writeSpan(qulonglong position, const std::shared_ptr<AbstractSpan> &span, char fill_byte=0);
    void writeChain(qulonglong position, const std::shared_ptr<SpanChain> &chain, char fill_byte=0);
    void remove(qulonglong position, qulonglong length);
    void clear();

    bool isModified()const;
    bool isRangeModified(qulonglong position, qulonglong length)const;

    void undo();
    void redo(int branch_id=-1);
    void addAction(const std::shared_ptr<AbstractUndoAction> &action);
    void beginComplexAction(const QString &title=QString());
    void endComplexAction();
    bool canUndo()const;
    bool canRedo()const;
    QList<int> getAlternativeBranchesIds()const;

    void save(const std::shared_ptr<AbstractDevice> &write_device=std::shared_ptr<AbstractDevice>(),
              bool switch_devices=false);
    bool checkCanQuickSave()const;

    const std::shared_ptr<SpanChain> exportRange(qulonglong position, qulonglong length, int ram_limit=-1)const;

signals:
    void dataChanged(qulonglong, qulonglong);
    void bytesInserted(qulonglong, qulonglong);
    void bytesRemoved(qulonglong, qulonglong);
    void resized(qulonglong);
    void canUndoChanged(bool);
    void canRedoChanged(bool);
    void isModifiedChanged(bool);
    void urlChanged(const QUrl &);
    void readOnlyChanged(bool);
    void fixedSizeChanged(bool);

protected:
    std::shared_ptr<AbstractDevice> _device;
    std::shared_ptr<SpanChain> _spanChain;
    std::shared_ptr<ComplexAction> _currentUndoAction;
    std::shared_ptr<ComplexAction> _rootAction;
    bool _undoDisabled;
    bool _fixedSize;
    bool _readOnly;
    int _currentAtomicOperationIndex;
    int _savepoint;
    std::shared_ptr<ReadWriteLock> _lock;

    void _insertChain(qulonglong position, const std::shared_ptr<SpanChain> &chain, char fill_byte, bool from_undo, int op_increment);
    void _remove(qulonglong position, qulonglong length, bool from_undo, int op_increment);
    void _writeChain(qulonglong position, const std::shared_ptr<SpanChain> &chain, char fill_byte, bool from_undo, int op_increment);
    void _incrementAtomicOperationIndex(int inc);
    QList<std::shared_ptr<PrimitiveDeviceSpan>> _prepareToUpdateDevice(const std::shared_ptr<AbstractDevice> &new_device);
    void _setSavepoint();

private slots:
    void _onDeviceReadOnlyChanged(bool);
};


class AbstractUndoAction : public std::enable_shared_from_this<AbstractUndoAction> {
    friend class ComplexAction;
public:
    AbstractUndoAction(const std::shared_ptr<Document> &document, const QString &title=QString());
    virtual ~AbstractUndoAction();

    std::shared_ptr<Document> getDocument();
    QString getTitle()const;

    std::shared_ptr<ComplexAction> getParentAction()const;
    void setParentAction(const std::shared_ptr<ComplexAction> &action);

    virtual void undo() = 0;
    virtual void redo() = 0;

private:
    std::shared_ptr<Document> _document;
    QString _title;
    std::weak_ptr<ComplexAction> _parentAction;
};


class ComplexAction : public AbstractUndoAction {
    /* ComplexAction stores sub-actions and allows undo them one-by-one or together. Also stores alternate branches
     * for undone actions.
     */
public:
    class Branch {
    public:
        Branch() : startIndex(), id(-1) {

        }

        QList<std::shared_ptr<AbstractUndoAction>> actions;
        int startIndex;
        int id;
    };

    ComplexAction(const std::shared_ptr<Document> &document, const QString &title=QString());

    void undoStep();
    void redoStep(int branch_id=-1);
    void undo();
    void redo();
    void addAction(const std::shared_ptr<AbstractUndoAction> &action);
    bool canUndo()const;
    bool canRedo()const;
    QList<int> alternativeBranchesIds()const;

private:
    QList<std::shared_ptr<AbstractUndoAction>> _subActions;
    int _currentStep; // index of subaction that will be undone by next call to CompexAction::undoStep.
                      // this index will be decremented with each call to undoStep, and incremented with call
                      // to redoStep (so all subactions with indexes >= _currentStep can be undone, and subactions
                      // with indexes < _currentIndex can be redone).
    QList<Branch> _branches;

    void _startNewBranch();
};


#endif // DOCUMENT_H
