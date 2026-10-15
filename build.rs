fn main() {
    println!("cargo:rerun-if-changed=web/index.html");
    println!("cargo:rerun-if-changed=web/icons/icon-192.png");
    println!("cargo:rerun-if-env-changed=PC_REMOTE_VERSION");
}
