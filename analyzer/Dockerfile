FROM archlinux

RUN yes | pacman -Sy iptables-nft

COPY target/x86_64-unknown-linux-musl/release/analyzer /analyzer

ENTRYPOINT ["/analyzer"]

