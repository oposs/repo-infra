# The prepared base of every ri-release-distro-packages build (D38). The
# project's own Containerfile is built on top of it with BASE set to this
# image, so the project names its build dependencies and nothing else.
#
# repos: the repositories a project expects on its release. On AlmaLinux many
# -devel packages live in CRB and many libraries in EPEL; a project that
# builds on Fedora would otherwise miss them on AlmaLinux. Debian, Ubuntu,
# Fedora and Alpine need nothing added.
#
# tools: the package of the dependency detector, distro-deps.sh.
#
# Built with no build context, so everything it needs lives in this file.
ARG IMAGE
FROM ${IMAGE} AS repos
RUN . /etc/os-release; \
    case " $ID $ID_LIKE " in \
      *" rhel "*) \
        dnf install -y epel-release \
        && crb enable \
        && dnf clean all ;; \
    esac

FROM repos AS tools
RUN . /etc/os-release; \
    case " $ID $ID_LIKE " in \
      *" debian "*) \
        apt-get update \
        && apt-get install -y --no-install-recommends dpkg-dev \
        && rm -rf /var/lib/apt/lists/* ;; \
      *" fedora "*) \
        dnf install -y rpm-build && dnf clean all ;; \
      *" alpine "*) \
        apk add --no-cache pax-utils ;; \
      *) echo "distro-base: no detector package for $ID" >&2; exit 1 ;; \
    esac
