Microhex is crossplatform hex-editing software based on Python and Qt.

In actual version the following features are available:
-   loading and saving files
-   creating new documents from scratch
-   editing data
-   insert and overwrite mode
-   hex view is highly configurable - you can easily add new columns and remove existing ones.
-   two predefined type of columns are available: integers column can interpret data as bytes, words, double or quad words, signed or unsigned, little or big endian; characters column interpret data as sequence of characters in one of >30 encodings including various Unicode formats (UTF-16, UF-32, UTF-8).
-   each column can have unlimited number of linked address bars displaying absolute or relative to fixed position address.
-   loading not entire file, but only specified range of bytes
-   freezing loaded data size (no operation that changes data size will be allowed)
-   loading file in read-only and read-write mode
-   loading very large files (size is limited only by free RAM) without memory and time overhead
-   files can be loaded into RAM (to keep data safe from changes made by another applications) or file data fill be read only when necessary.
-   copy and paste (only data copied from Microhex yet)
-   undo and redo operations not limited to state where file was saved (you can undo changes even after you have saved it to disk)
-   translation support (English and Russian translations are provided)
-   hex view zooming (Ctrl+Wheel)
-   hex view theming (not available via GUI yet)

See INSTALL file to get instructions how to install and run application.

Currently not all application settings can be changed via GUI, but you can manually edit configuration files.  Settings are stored in directory:
-   Linux: ~/.microhex
-   Windows: depends on OS settings, in most cases C:/Documents and Settings/%username%/Application Data/microhex on Windows XP and earlier or C:/Users/%username%/Application Data/microhex on Windows 7 and later. Registry is never affected.

Configurable settings are stored in microhex.conf file in JSON format. Sample of configuration file with commentaries can be found in docs/microhex.conf file.
