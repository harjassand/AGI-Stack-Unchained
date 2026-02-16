#![forbid(unsafe_code)]

mod brain;
mod canon;
mod cli;
mod hash;
mod kernel_sys;
mod paths;
mod pinning;
mod suite;

fn main() {
    let exit_code = match run() {
        Ok(code) => code,
        Err(reason) => {
            eprintln!("{reason}");
            30
        }
    };
    kernel_sys::exit(exit_code);
}

fn run() -> Result<i32, String> {
    let args = cli::parse_args()?;
    match args.command {
        cli::Command::BrainSuite { suitepack, out_dir } => {
            suite::brain_suite::execute_brain_suite(&suitepack, &out_dir)
        }
    }
}
