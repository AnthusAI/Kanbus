//! Emit resolved standup window settings as JSON for dual-runtime parity checks.

use std::env;
use std::path::PathBuf;

use kanbus::standup::load_standup_configuration;
use kanbus::standup_window::{
    canonicalize_standup_timezone_name, resolve_standup_window_settings, StandupWindowOverrides,
};
use serde_json::json;

fn main() {
    let root = env::args().nth(1).map(PathBuf::from).unwrap_or_else(|| {
        eprintln!("usage: standup_window_probe <repo-root>");
        std::process::exit(2);
    });
    let configuration = load_standup_configuration(&root).unwrap_or_else(|error| {
        eprintln!("{error}");
        std::process::exit(1);
    });
    let settings =
        resolve_standup_window_settings(&configuration, None, &StandupWindowOverrides::default())
            .unwrap_or_else(|error| {
                eprintln!("{error}");
                std::process::exit(1);
            });
    let payload = json!({
        "window": settings.window,
        "lookback": settings.lookback,
        "lookback_hours": settings.lookback_hours,
        "skip_weekends": settings.skip_weekends,
        "timezone": canonicalize_standup_timezone_name(settings.timezone.name()),
    });
    println!("{}", payload);
}
