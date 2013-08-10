#ifndef CLIPBOARD_H
#define CLIPBOARD_H

#include <QtGlobal>
#include <memory>

class Document;
class SpanChain;

namespace Clipboard {

void setData(const std::shared_ptr<const Document> &document, qulonglong position, qulonglong length);
std::shared_ptr<SpanChain> getData();
bool hasMicrohexData();

}

#endif // CLIPBOARD_H
