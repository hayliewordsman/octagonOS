/*
    SPDX-FileCopyrightText: 2026 The octagonOS Project
    SPDX-License-Identifier: Apache-2.0

    Load the FacetUI Plasma style with Plasma's own SVG engine, and check that
    each surface really has the properties FacetUI requires.

        plasma-probe <theme-name> <out.png> <image-path>=<alpha> ...

    WHY THIS EXISTS

    A Plasma theme is a directory of SVGs whose element ids matter. Nothing
    checks them: a missing `bottomright`, an element whose bounding box touches
    its neighbour, a hairline that stops short of a tile's edge -- each one
    renders something, and the something is wrong in a way that reads as a
    rendering bug rather than a theme bug. The dotted hairline this found was
    exactly that.

    Reading the SVGs with an XML parser proves the ids are spelled right. Only
    the real engine proves the engine can use them.

    So each surface is painted TWICE, over black and over white, and the two
    results are compared:

      - the difference between them gives the surface's actual alpha, which is
        the only way to tell a translucent surface from an opaque one that
        happens to be dark;
      - a row just inside the top edge is compared with the interior, which is
        how a missing or clipped hairline shows up.

    Exits non-zero if a frame fails to load, or if a surface is not as
    translucent as it claims, or has no boundary.
*/

#include <QGuiApplication>
#include <QImage>
#include <QPainter>
#include <QFont>
#include <QTextStream>

// KSvg, not Plasma. Plasma::Svg and Plasma::Theme were moved out of libplasma
// into the KSvg framework for Plasma 6: the classes are KSvg::FrameSvg and
// KSvg::ImageSet, and libplasma no longer installs an Svg header at all. The
// theme FORMAT is unchanged -- still plasma/desktoptheme -- which is why code
// written from Plasma 5 documentation looks right and does not compile.
#include <KSvg/FrameSvg>
#include <KSvg/ImageSet>

#include <cmath>

namespace
{

constexpr int kWidth = 260;
constexpr int kHeight = 120;

/// Paint one frame at kWidth x kHeight over a flat backdrop.
QImage render(KSvg::FrameSvg &frame, const QColor &backdrop)
{
    QImage img(kWidth, kHeight, QImage::Format_ARGB32_Premultiplied);
    img.fill(backdrop);
    QPainter p(&img);
    frame.resizeFrame(QSizeF(kWidth, kHeight));
    frame.paintFrame(&p, QPointF(0, 0));
    p.end();
    return img;
}

} // namespace

/// Compose the theme's surfaces over a supplied wallpaper, for the README.
///
/// Separate from the checking path on purpose: this makes a picture, it does
/// not decide anything. A preview that also reported success would be a check
/// nobody could fail.
static int compose(const QString &themeName, const QString &wallpaperPath,
                   const QString &outPath, QTextStream &out)
{
    QImage wall(wallpaperPath);
    if (wall.isNull()) {
        out << "[FAIL] could not read " << wallpaperPath << "\n";
        return 2;
    }
    KSvg::ImageSet set;
    set.setBasePath(QStringLiteral("plasma/desktoptheme"));
    set.setImageSetName(themeName);
    if (set.imageSetName() != themeName) {
        out << "[FAIL] KSvg did not accept the theme " << themeName << "\n";
        return 1;
    }

    QPainter p(&wall);
    p.setRenderHint(QPainter::Antialiasing);

    struct Item {
        const char *path;
        int x, y, w, h;
    };
    const Item items[] = {
        {"widgets/panel-background", 0, 0, wall.width(), 40},
        {"widgets/background", 40, 92, 230, 232},
        {"dialogs/background", 320, 150, 560, 250},
        {"widgets/tooltip", wall.width() - 280, wall.height() - 110, 240, 58},
    };
    for (const Item &it : items) {
        KSvg::FrameSvg frame;
        frame.setImageSet(&set);
        frame.setImagePath(QString::fromUtf8(it.path));
        if (!frame.isValid()) {
            out << "[FAIL] " << it.path << " is not a valid frame\n";
            return 1;
        }
        frame.resizeFrame(QSizeF(it.w, it.h));
        frame.paintFrame(&p, QPointF(it.x, it.y));
    }

    p.setPen(QColor(238, 243, 252));
    p.setFont(QFont(QStringLiteral("DejaVu Sans"), 11, QFont::Bold));
    p.drawText(QPoint(18, 26), QStringLiteral("octagonOS"));
    p.drawText(QPoint(wall.width() - 86, 26), QStringLiteral("21:41"));
    p.drawText(QPoint(352, 200), QStringLiteral("Apply these display settings?"));

    p.setFont(QFont(QStringLiteral("DejaVu Sans"), 10));
    p.setPen(QColor(186, 206, 236));
    p.drawText(QPoint(352, 230), QStringLiteral("Reverting in 15 seconds."));
    p.setPen(QColor(150, 190, 245));
    p.drawText(QPoint(716, 376), QStringLiteral("Revert"));
    p.drawText(QPoint(796, 376), QStringLiteral("Keep"));

    p.setPen(QColor(226, 236, 250));
    const char *menu[] = {"New window", "Open recent", "Preferences", "Quit"};
    for (int i = 0; i < 4; i++) {
        p.drawText(QPoint(66, 132 + i * 46), QString::fromUtf8(menu[i]));
    }
    p.drawText(QPoint(wall.width() - 258, wall.height() - 72),
               QStringLiteral("Shows a tooltip"));
    p.end();

    if (!wall.save(outPath)) {
        out << "[FAIL] could not write " << outPath << "\n";
        return 2;
    }
    out << "[*] wrote " << outPath << "\n";
    return 0;
}

int main(int argc, char **argv)
{
    // offscreen: there is no display, and none is needed to rasterise SVG.
    qputenv("QT_QPA_PLATFORM", "offscreen");
    QGuiApplication app(argc, argv);
    QTextStream out(stdout);

    if (argc == 5 && QString::fromUtf8(argv[1]) == QLatin1String("--compose")) {
        return compose(QString::fromUtf8(argv[2]), QString::fromUtf8(argv[3]),
                       QString::fromUtf8(argv[4]), out);
    }

    if (argc < 4) {
        out << "usage: plasma-probe <theme> <out.png> <image-path>=<alpha> ...\n"
               "       plasma-probe --compose <theme> <wallpaper.png> <out.png>\n";
        return 2;
    }
    const QString themeName = QString::fromUtf8(argv[1]);
    const QString outPath = QString::fromUtf8(argv[2]);

    KSvg::ImageSet imageSet;
    // The base path is what makes this a PLASMA theme rather than some other
    // KSvg image set; KSvg itself is generic.
    imageSet.setBasePath(QStringLiteral("plasma/desktoptheme"));
    imageSet.setImageSetName(themeName);
    if (imageSet.imageSetName() != themeName) {
        out << "[FAIL] KSvg did not accept the theme name: asked for "
            << themeName << ", got " << imageSet.imageSetName() << "\n"
            << "       The theme is not in a path it searches, or its\n"
               "       metadata.json is not one it will load.\n";
        return 1;
    }

    int failures = 0;
    QList<QImage> gallery;
    QStringList labels;

    for (int i = 3; i < argc; i++) {
        const QString arg = QString::fromUtf8(argv[i]);
        const int eq = arg.lastIndexOf(QLatin1Char('='));
        if (eq < 0) {
            out << "[FAIL] bad argument '" << arg << "', want path=alpha\n";
            return 2;
        }
        const QString path = arg.left(eq);
        const double wantAlpha = arg.mid(eq + 1).toDouble();

        KSvg::FrameSvg frame;
        frame.setImageSet(&imageSet);
        frame.setImagePath(path);

        if (!frame.isValid()) {
            out << "[FAIL] " << path << ": KSvg says this is not a valid frame\n";
            failures++;
            continue;
        }

        const QImage onBlack = render(frame, QColor(0, 0, 0));
        const QImage onWhite = render(frame, QColor(255, 255, 255));

        // --- translucency ---------------------------------------------------
        //
        // Over black the surface shows alpha*surface; over white it shows
        // alpha*surface + (1-alpha)*255. The difference is (1-alpha)*255, and
        // it is the ONLY way to distinguish a translucent surface from an
        // opaque dark one -- which is what this looked like by eye.
        const QPoint mid(kWidth / 2, kHeight / 2);
        const int black = qRed(onBlack.pixel(mid));
        const int white = qRed(onWhite.pixel(mid));
        const double gotAlpha = 1.0 - (white - black) / 255.0;

        if (std::abs(gotAlpha - wantAlpha) > 0.03) {
            out << "[FAIL] " << path << ": alpha is " << QString::number(gotAlpha, 'f', 3)
                << ", theme says " << QString::number(wantAlpha, 'f', 3) << "\n";
            failures++;
        } else {
            out << "[ok]   " << path << " alpha "
                << QString::number(gotAlpha, 'f', 3) << "  margins t/r/b/l "
                << frame.marginSize(KSvg::FrameSvg::TopMargin) << "/"
                << frame.marginSize(KSvg::FrameSvg::RightMargin) << "/"
                << frame.marginSize(KSvg::FrameSvg::BottomMargin) << "/"
                << frame.marginSize(KSvg::FrameSvg::LeftMargin);
        }

        // --- the hairline ---------------------------------------------------
        //
        // Sampled across the middle of the top edge, away from the corners, on
        // the black backdrop where a light line has the most contrast. The
        // brightest row in the first few pixels should stand clear of the
        // interior; if it does not, the boundary is missing or was clipped.
        int brightest = 0, brightestRow = -1;
        for (int y = 0; y < 6; y++) {
            const int v = qRed(onBlack.pixel(kWidth / 2, y));
            if (v > brightest) {
                brightest = v;
                brightestRow = y;
            }
        }
        const int interior = qRed(onBlack.pixel(kWidth / 2, kHeight / 2));
        if (brightest - interior < 6) {
            out << "\n[FAIL] " << path << ": no hairline at the top edge "
                << "(brightest row " << brightestRow << " is " << brightest
                << ", interior is " << interior << ")\n"
                << "       Without a boundary a translucent surface dissolves "
                   "into\n       whatever is behind it. That is the third "
                   "thing FacetUI\n       requires, and blur and tint are "
                   "wasted without it.\n";
            failures++;
        } else {
            out << "  hairline +" << (brightest - interior) << "\n";
        }

        // Also check it is CONTINUOUS.
        //
        // A hairline drawn short of a border tile's end leaves a gap at every
        // repeat: a DOTTED line, not a missing one, so the check above passes
        // and the theme is still wrong. An absolute threshold does not find it
        // either -- antialiasing leaves a gap pixel part-lit, and part-lit is
        // still brighter than the interior. What a dotted line really has is
        // VARIATION along the row, so that is what is measured.
        int lineMin = 1 << 20, lineMax = 0;
        for (int x = 24; x < kWidth - 24; x++) {
            const int v = qRed(onBlack.pixel(x, brightestRow)) - interior;
            lineMin = qMin(lineMin, v);
            lineMax = qMax(lineMax, v);
        }
        if (qEnvironmentVariableIsSet("PROBE_DEBUG_ROW")) {
            out << "       row " << brightestRow << ":";
            for (int x = 8; x < kWidth - 8; x += 6) {
                out << " " << (qRed(onBlack.pixel(x, brightestRow)) - interior);
            }
            out << "\n";
        }
        if (lineMax > 0 && lineMin < lineMax * 7 / 10) {
            out << "[FAIL] " << path << ": the hairline varies along its length "
                << "(" << lineMin << " to " << lineMax << ") -- it is dotted, "
                   "not solid.\n       A border element whose line stops short "
                   "of the tile edge does\n       this: Plasma repeats the "
                   "element, and every repeat leaves a gap.\n";
            failures++;
        }

        // --- the corners ----------------------------------------------------
        //
        // A frame element whose id is misspelled is not an error to KSvg: it
        // simply draws nothing there, and the frame comes out with a bite
        // taken out of one corner. Nothing above looks at the corners, so this
        // is where that is caught -- each corner box must carry a reasonable
        // share of the surface the middle does.
        // The box is SMALL and sits right in the extreme corner. A larger one
        // overlaps the two border elements meeting there, which keep it lit
        // even when the corner itself is gone -- a 12x12 box missed exactly
        // that, and reported a corner that was not drawn as fine.
        static const int kCorner = 6;
        static const char *cornerName[] = {"topleft", "topright",
                                           "bottomleft", "bottomright"};
        const QPoint cornerAt[] = {
            QPoint(0, 0), QPoint(kWidth - kCorner, 0),
            QPoint(0, kHeight - kCorner),
            QPoint(kWidth - kCorner, kHeight - kCorner),
        };
        double shares[4] = {0, 0, 0, 0};
        for (int c = 0; c < 4; c++) {
            long sum = 0;
            for (int dy = 0; dy < kCorner; dy++) {
                for (int dx = 0; dx < kCorner; dx++) {
                    sum += qRed(onBlack.pixel(cornerAt[c].x() + dx,
                                              cornerAt[c].y() + dy));
                }
            }
            const double share =
                double(sum) / (kCorner * kCorner) / qMax(1, interior);
            shares[c] = share;
            if (qEnvironmentVariableIsSet("PROBE_DEBUG_ROW")) {
                out << "       corner " << cornerName[c] << " share "
                    << QString::number(share, 'f', 3) << "\n";
            }
            // A rounded corner of this radius covers about a third of the box;
            // a missing element covers none of it. The bar sits between.
            if (share < 0.12) {
                out << "[FAIL] " << path << ": the " << cornerName[c]
                    << " corner is not drawn (" << QString::number(share, 'f', 2)
                    << " of the interior's coverage).\n       A frame element "
                       "whose id is misspelled draws nothing, and KSvg\n"
                       "       does not consider that an error.\n";
                failures++;
            }
        }

        // The four corners are the same shape in this theme, so they must
        // cover the same amount. Comparing them with each other catches a
        // single malformed one -- an arc with the wrong sweep flag draws a
        // leaf rather than a corner, and a leaf still covers enough of its box
        // to pass the absolute test above.
        {
            double mean = 0;
            for (double v : shares) {
                mean += v / 4.0;
            }
            for (int c = 0; c < 4; c++) {
                if (mean > 0.01 && std::abs(shares[c] - mean) > mean * 0.25) {
                    out << "[FAIL] " << path << ": the " << cornerName[c]
                        << " corner covers "
                        << QString::number(shares[c], 'f', 2)
                        << " where the four average "
                        << QString::number(mean, 'f', 2)
                        << ".\n       The four corners of this theme are the "
                           "same shape, so one that\n       differs is "
                           "malformed -- an arc with the wrong sweep flag "
                           "draws a\n       leaf instead of a corner.\n";
                    failures++;
                }
            }
        }

        // --- seams ------------------------------------------------------
        //
        // Where a corner element meets the two borders beside it, the surface
        // must simply continue. It does not, if anything inflates the corner's
        // bounding box: Plasma sizes each element from that box, so the tile
        // gets squeezed and its last row and column come out half-covered. A
        // stroked outline does exactly that -- the seam measured 9 against the
        // surface's 17 -- and over a bright wallpaper it reads as a light
        // notch at every corner.
        //
        // A seam is a one-pixel dip with higher values on both sides, so that
        // is what is looked for, along two lines that cross every corner
        // region.
        {
            int seams = 0;
            const int rows[] = {3, kHeight - 4};
            for (int r = 0; r < 2; r++) {
                const int y = rows[r];
                for (int x = 3; x < kWidth - 3; x++) {
                    const int here = qRed(onBlack.pixel(x, y));
                    const int before = qRed(onBlack.pixel(x - 2, y));
                    const int after = qRed(onBlack.pixel(x + 2, y));
                    const int lower = qMin(before, after);
                    if (lower > 0 && here < lower * 85 / 100) {
                        seams++;
                    }
                }
            }
            if (seams) {
                out << "[FAIL] " << path << ": the surface has " << seams
                    << " seam(s) -- a column of reduced coverage with full\n"
                       "       coverage on both sides. A corner element whose "
                       "bounding box is\n       larger than its tile does "
                       "this: Plasma squeezes the tile to fit\n       and the "
                       "last row and column fall short of the borders.\n";
                failures++;
            }
        }

        gallery.append(onBlack);
        labels.append(path);
    }

    // A sheet, over a mid grey, for looking at.
    if (!gallery.isEmpty()) {
        const int pad = 16;
        QImage sheet(kWidth + pad * 2,
                     (kHeight + pad) * gallery.size() + pad,
                     QImage::Format_ARGB32_Premultiplied);
        sheet.fill(QColor(96, 102, 120));
        QPainter p(&sheet);
        int y = pad;
        for (const QImage &img : gallery) {
            // Repaint over the sheet's own grey rather than pasting the black
            // version, so the picture shows what translucency looks like.
            p.drawImage(QPoint(pad, y), img);
            y += kHeight + pad;
        }
        p.end();
        if (!sheet.save(outPath)) {
            out << "[FAIL] could not write " << outPath << "\n";
            return 2;
        }
        out << "[*] wrote " << outPath << "\n";
    }

    return failures ? 1 : 0;
}
