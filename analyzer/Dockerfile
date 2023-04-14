FROM archlinux

RUN pacman -Sy --noconfirm iptables

COPY target/x86_64-unknown-linux-musl/release/analyzer /analyzer

ENTRYPOINT ["/analyzer"]

