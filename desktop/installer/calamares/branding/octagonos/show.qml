/* The installer's slideshow.
 *
 * Deliberately three plain statements rather than marketing: someone reading
 * this is waiting for a progress bar, and the useful thing to tell them is
 * what they are getting and what it does not do yet.
 */
import QtQuick 2.5
import calamares.slideshow 1.0

Presentation {
    id: presentation

    Timer {
        interval: 8000
        running: presentation.activatedInCalamares
        repeat: true
        onTriggered: presentation.goToNextSlide()
    }

    Slide {
        Text {
            anchors.centerIn: parent
            horizontalAlignment: Text.AlignHCenter
            font.pixelSize: 22
            color: "#dfe3ea"
            text: "octagonOS\n\nPlasma 6 on Wayland, themed throughout by FacetUI."
        }
    }

    Slide {
        Text {
            anchors.centerIn: parent
            horizontalAlignment: Text.AlignHCenter
            font.pixelSize: 20
            color: "#dfe3ea"
            text: "Glass is three things at once:\nblur behind, translucency, and a hairline edge.\n\nAny one of them missing wastes the other two."
        }
    }

    Slide {
        Text {
            anchors.centerIn: parent
            horizontalAlignment: Text.AlignHCenter
            font.pixelSize: 20
            color: "#dfe3ea"
            text: "This is a beta.\n\nThe compositor effect has been seen running on a booted\nmachine. It has not been through sustained use\non varied hardware."
        }
    }
}
