#ifndef BASE_H
#define BASE_H

#include <stdexcept>
#include <QString>
#include <string>

class BaseException : public std::logic_error {
public:
    BaseException(const QString &what) : std::logic_error(std::string(what.toUtf8().constData())) {

    }
};

extern const qulonglong QULONGLONG_MAX;

#endif // BASE_H
