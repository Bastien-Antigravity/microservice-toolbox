use microservice_toolbox::config::loader::AppConfig;
use std::env;

fn main() {
    let args: Vec<String> = env::args().collect();
    if args.len() < 3 {
        println!("Usage: expansion_check <profile> <key>");
        std::process::exit(1);
    }

    let profile = &args[1];
    let key = &args[2];

    match AppConfig::load_config(profile, None) {
        Ok(ac) => {
            let val = ac.get_local(key);
            match val {
                Some(v) => {
                    if let Some(s) = v.as_str() {
                        print!("VALUE:{}", s);
                    } else {
                        print!("VALUE:{:?}", v);
                    }
                }
                None => {
                    print!("VALUE:");
                }
            }
        }
        Err(e) => {
            print!("VALUE:ERROR_{}", e);
        }
    }
}
