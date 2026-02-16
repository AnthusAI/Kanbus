fn main() {
    // Print post-install instructions when building for release
    if std::env::var("PROFILE").unwrap_or_default() == "release" {
        println!("cargo:warning=");
        println!("cargo:warning=Kanbus installed successfully!");
        println!("cargo:warning=");
        println!("cargo:warning=Optional: Create shortcuts 'kbs' and 'kbsc' by running:");
        println!("cargo:warning=  curl -sSL https://raw.githubusercontent.com/AnthusAI/Kanbus/main/rust/install-aliases.sh | bash");
        println!("cargo:warning=");
    }
}
