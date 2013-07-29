#ifndef DOCUMENT_H
#define DOCUMENT_H

#include <exception>
#include <QObject>
#include <QUrl>
#include <QReadWriteLock>
#include <QByteArray>


class SpanChain;
class AbstractUndoAction;
class AbstractSpan;
class ComplexAction;
class AbstractDevice;


class DocumentError {
public:
    DocumentError(const QString &desc=QString()) : _desc(desc) { }
private:
    QString _desc;
};


class Document : public QObject {
    Q_OBJECT
    friend class InsertAction;
    friend class RemoveAction;
public:
    Document(AbstractDevice *device=nullptr);
    ~Document();

    AbstractDevice *device()const;
    QUrl url()const;
    qulonglong length()const;
    bool fixedSize()const;
    void setFixedSize(bool fixed_size);
    bool readOnly()const;
    void setReadOnly(bool read_only);

    QByteArray read(qulonglong position, qulonglong length)const;
    QByteArray readAll()const;

    void insertSpan(qulonglong position, AbstractSpan *span, char fill_byte=0);
    void insertChain(qulonglong position, SpanChain *chain, char fill_byte=0);
    void appendSpan(AbstractSpan *span);
    void appendChain(SpanChain *chain);
    void writeSpan(qulonglong position, AbstractSpan *span, char fill_byte=0);
    void writeChain(qulonglong position, SpanChain *chain, char fill_byte=0);
    void remove(qulonglong position, qulonglong length);
    void clear();

    bool isModified()const;
    bool isRangeModified(qulonglong position, qulonglong length)const;

    void undo();
    void redo(int branch_id=-1);
    void addAction(AbstractUndoAction *action);
    void beginComplexAction(const QString &title=QString());
    void endComplexAction();
    bool canUndo()const;
    bool canRedo()const;
    QList<int> alternativeBranchesIds()const;

    void save(AbstractDevice *write_device, bool switch_devices=false);
    bool checkCanQuickSave()const;

signals:
    void dataChanged(qulonglong, qulonglong);
    void bytesInserted(qulonglong, qulonglong);
    void bytesRemoved(qulonglong, qulonglong);
    void resized(qulonglong);
    void canUndoChanged(bool);
    void canRedoChanged(bool);
    void isModifiedChanged(bool);
    void urlChanged(const QUrl &);

protected:
    AbstractDevice *_device;
    QReadWriteLock *_lock;
    SpanChain *_spanChain;
    ComplexAction *_currentUndoAction;
    bool _undoDisabled;
    bool _fixedSize;
    bool _readOnly;
    qulonglong _currentAtomicOperationIndex;
    qulonglong _savepoint;

    void _insertChain(qulonglong position, SpanChain *chain, char fill_byte, bool undo);
    void _remove(qulonglong position, qulonglong length, bool undo);
    void _incrementAtomicOperationIndex(int inc);
    void _prepareToUpdateDevice(AbstractDevice *new_device);
    void _setSavepoint();
};


class AbstractUndoAction : public QObject {
    friend class ComplexAction;
public:
    AbstractUndoAction(Document *document, const QString &title=QString());
    virtual ~AbstractUndoAction();

    Document *document();
    QString title()const;

    ComplexAction *parentAction()const;

    virtual void undo() = 0;
    virtual void redo() = 0;

private:
    Document *_document;
    QString _title;
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

        QList<AbstractUndoAction *> actions;
        int startIndex;
        int id;
    };

    ComplexAction(Document *document, const QString &title=QString());

    void undoStep();
    void redoStep(int branch_id=-1);
    void undo();
    void redo();
    void addAction(AbstractUndoAction *action);
    bool canUndo()const;
    bool canRedo()const;
    QList<int> alternativeBranchesIds()const;

private:
    QList<AbstractUndoAction *> _subActions;
    int _currentStep; // index of subaction that will be undone by next call to CompexAction::undoStep.
                      // this index will be decremented with each call to undoStep, and incremented with call
                      // to redoStep (so all subactions with indexes >= _currentStep can be undone, and subactions
                      // with indexes < _currentIndex can be redone).
    QList<Branch> _branches;

    void _startNewBranch();
};


#endif // DOCUMENT_H
