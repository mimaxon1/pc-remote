fn main() {
    println!("cargo:rerun-if-changed=web/index.html");
    println!("cargo:rerun-if-changed=web/icons/icon-192.png");
    println!("cargo:rerun-if-changed=web/favicon.ico");
    println!("cargo:rerun-if-env-changed=PC_REMOTE_VERSION");
    #[cfg(target_os = "windows")]
    winresource::WindowsResource::new()
        .set_icon("web/favicon.ico")
        .set("ProductName", "PC Remote")
        .set("FileDescription", "PC Remote")
        .compile()
        .expect("Could not embed the Windows application icon");
}
