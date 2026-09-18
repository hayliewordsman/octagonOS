/*
    SPDX-FileCopyrightText: 2026 The octagonOS Project
    SPDX-License-Identifier: Apache-2.0

    Resolve the FacetUI icon theme with Qt's own icon loader.

        icon-probe <theme-dir's parent> <theme-name> <size> <name> ...

    WHY THIS EXISTS

    A freedesktop icon theme is a directory whose index.theme has to agree with
    what is on disk. Nothing checks that. A directory listed but absent, a size
    declared that does not match the pixels, an icon named for a context it is
    not in -- each one resolves to SOMETHING, because the spec says to fall
    back, and falling back is indistinguishable from working until you notice
    every icon is Breeze's.

    So this asks Qt for each icon and then checks what came back:

      - the icon exists in THIS theme, not in one it inherits from;
      - the pixmap is the size that was asked for;
      - it is not blank;
      - a name the theme does not define still resolves, through Inherits,
        which is the mechanism that makes a partial theme usable at all.

    The last two matter together: a theme that resolves everything to a blank
    pixmap passes a "does it resolve" test perfectly.
*/

#include <QDir>
#include <QFile>
#include <QGuiApplication>
#include <QIcon>
#include <QImage>
#include <QPixmap>
#include <QTextStream>

int main(int argc, char **argv)
{
    qputenv("QT_QPA_PLATFORM", "offscreen");
    QGuiApplication app(argc, argv);
    QTextStream out(stdout);

    if (argc < 5) {
        out << "usage: icon-probe <search-path> <theme> <size> <name> ...\n";
        return 2;
    }
    const QString searchPath = QString::fromUtf8(argv[1]);
    const QString themeName = QString::fromUtf8(argv[2]);
    const int size = QString::fromUtf8(argv[3]).toInt();

    // The theme's own directory, then the system ones.
    //
    // Two mistakes are easy here and both make a correct theme look broken.
    // Substituting for Qt's default paths instead of adding to them leaves
    // every inherited theme unreachable. And Qt's defaults come from
    // XDG_DATA_DIRS, which is unset in a bare container -- so the system
    // themes are not on the list at all, and the inheritance check below fails
    // for want of a Breeze to inherit from. The spec's documented default for
    // an unset XDG_DATA_DIRS is used instead of assuming the environment has
    // one.
    QStringList paths = QIcon::themeSearchPaths();
    QString dataDirs = qEnvironmentVariable("XDG_DATA_DIRS");
    if (dataDirs.isEmpty()) {
        dataDirs = QStringLiteral("/usr/local/share:/usr/share");
    }
    const QString home = QDir::homePath();
    QStringList systemPaths{home + QStringLiteral("/.icons"),
                            home + QStringLiteral("/.local/share/icons")};
    for (const QString &dir : dataDirs.split(QLatin1Char(':'), Qt::SkipEmptyParts)) {
        systemPaths << dir + QStringLiteral("/icons");
    }
    for (const QString &p : systemPaths) {
        if (!paths.contains(p)) {
            paths << p;
        }
    }
    paths.prepend(searchPath);
    QIcon::setThemeSearchPaths(paths);
    QIcon::setThemeName(themeName);
    if (QIcon::themeName() != themeName) {
        out << "[FAIL] Qt did not accept the theme: asked for " << themeName
            << ", got " << QIcon::themeName() << "\n";
        return 1;
    }
    out << "[*] theme " << QIcon::themeName() << " from " << searchPath << "\n";
    if (qEnvironmentVariableIsSet("ICON_PROBE_DEBUG")) {
        out << "    search paths: " << QIcon::themeSearchPaths().join(", ") << "\n";
        out << "    fallback theme: " << QIcon::fallbackThemeName() << "\n";
    }

    int failures = 0;
    int checked = 0;

    for (int i = 4; i < argc; i++) {
        const QString name = QString::fromUtf8(argv[i]);

        // hasThemeIcon() cannot answer "is this OURS": it returns true for an
        // icon reached through Inherits, so a theme that defined nothing at
        // all would pass it for every name. The file on disk is the only
        // authority, so the pixmap Qt hands back is compared against it. That
        // also catches an index.theme whose declared Size does not match the
        // directory it names -- Qt would resolve the name from some other
        // size and the comparison fails.
        const QString own = QStringLiteral("%1/%2/apps/%3/%4.png")
                                .arg(searchPath, themeName)
                                .arg(size)
                                .arg(name);
        const QImage onDisk(own);
        if (onDisk.isNull()) {
            out << "[FAIL] " << name << " has no file at " << own << "\n";
            failures++;
            continue;
        }

        const QIcon icon = QIcon::fromTheme(name);
        if (icon.isNull()) {
            out << "[FAIL] " << name << " resolved to a null icon\n";
            failures++;
            continue;
        }

        const QPixmap pm = icon.pixmap(size, size);
        if (pm.width() != size || pm.height() != size) {
            out << "[FAIL] " << name << " at " << size << " came back "
                << pm.width() << "x" << pm.height()
                << " -- index.theme declares a size the files do not have\n";
            failures++;
            continue;
        }

        const QImage img = pm.toImage().convertToFormat(QImage::Format_ARGB32);

        // Is this the file we shipped, or one from an inherited theme?
        {
            // Compared PREMULTIPLIED, both sides. A QPixmap holds
            // premultiplied colour, so converting it to plain ARGB32 divides
            // the colour back out by the alpha -- which is lossy wherever the
            // alpha is partial. On an octagon that is the entire antialiased
            // rim, and it put the average difference at 20/255 for an icon
            // that was pixel-identical in the middle.
            const QImage a = pm.toImage().convertToFormat(
                QImage::Format_ARGB32_Premultiplied);
            const QImage want = onDisk.convertToFormat(
                QImage::Format_ARGB32_Premultiplied);
            long diff = 0;
            for (int y = 0; y < a.height(); y++) {
                for (int x = 0; x < a.width(); x++) {
                    const QRgb p1 = a.pixel(x, y);
                    const QRgb p2 = want.pixel(x, y);
                    diff += qAbs(qRed(p1) - qRed(p2))
                            + qAbs(qGreen(p1) - qGreen(p2))
                            + qAbs(qBlue(p1) - qBlue(p2))
                            + qAbs(qAlpha(p1) - qAlpha(p2));
                }
            }
            const double perPixel = double(diff) / (a.width() * a.height()) / 4.0;
            if (perPixel > 2.0) {
                out << "[FAIL] " << name << " at " << size << " is not the file "
                    << "this theme ships (differs by "
                    << QString::number(perPixel, 'f', 1) << "/255 per channel).\n"
                    << "       Qt resolved the name somewhere else -- an "
                       "inherited theme, or a\n       different size than "
                       "index.theme claims for this directory.\n";
                failures++;
                continue;
            }
        }

        // Not blank, and not a solid block either. An icon theme that renders
        // every name as the same filled square would pass every check above.
        long opaque = 0;
        long lumaSum = 0;
        int lumaMin = 255, lumaMax = 0;
        for (int y = 0; y < img.height(); y++) {
            for (int x = 0; x < img.width(); x++) {
                const QRgb p = img.pixel(x, y);
                if (qAlpha(p) > 24) {
                    opaque++;
                    const int l = qGray(p);
                    lumaSum += l;
                    lumaMin = qMin(lumaMin, l);
                    lumaMax = qMax(lumaMax, l);
                }
            }
        }
        const double cover = double(opaque) / (img.width() * img.height());
        if (cover < 0.25) {
            out << "[FAIL] " << name << " at " << size << " is "
                << QString::number(cover * 100, 'f', 1)
                << "% covered -- effectively blank\n";
            failures++;
            continue;
        }
        if (lumaMax - lumaMin < 24) {
            out << "[FAIL] " << name << " at " << size << " has no contrast "
                << "(luma " << lumaMin << ".." << lumaMax << ") -- a flat "
                << "block, not an icon\n";
            failures++;
            continue;
        }
        checked++;
    }

    // Inheritance. A theme this size only works because everything it does not
    // define falls through to another theme; if that is broken, the desktop
    // loses every icon this does not draw.
    const QString borrowed = QStringLiteral("edit-undo");
    const QString borrowedOwn = QStringLiteral("%1/%2/apps/%3/%4.png")
                                    .arg(searchPath, themeName)
                                    .arg(size)
                                    .arg(borrowed);
    if (QFile::exists(borrowedOwn)) {
        out << "[note] " << borrowed << " is defined by this theme, so it "
            << "cannot test inheritance\n";
    } else if (QIcon::fromTheme(borrowed).isNull()) {
        out << "[FAIL] " << borrowed << " resolves to nothing. Inherits is "
            << "not working, so every icon this theme does not\n"
            << "       define is lost rather than falling back.\n";
        failures++;
    } else {
        out << "[ok]   " << borrowed << " falls through to an inherited theme\n";
    }

    if (failures) {
        out << "\nFAILED: " << failures << " problem(s)\n";
        return 1;
    }
    out << "[ok]   " << checked << " icons resolve in this theme at " << size
        << "px, sized and drawn\n";
    return 0;
}
