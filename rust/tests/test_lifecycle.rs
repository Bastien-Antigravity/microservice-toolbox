use microservice_toolbox::lifecycle::new_manager;
use std::sync::Arc;
use tokio::sync::Mutex;

#[tokio::test]
async fn test_lifecycle_lifo_order() {
    let manager = new_manager(None);
    let order = Arc::new(Mutex::new(Vec::new()));

    let order_clone1 = order.clone();
    manager.register("cleanup1", move || {
        let oc = order_clone1.clone();
        async move {
            oc.lock().await.push(1);
            Ok(())
        }
    }).await;

    let order_clone2 = order.clone();
    manager.register("cleanup2", move || {
        let oc = order_clone2.clone();
        async move {
            oc.lock().await.push(2);
            Ok(())
        }
    }).await;

    // Simulate shutdown by manually calling the public cleanup executor
    manager.execute_cleanups().await;

    let final_order = order.lock().await;
    // LIFO: cleanup2 (2) then cleanup1 (1)
    assert_eq!(*final_order, vec![2, 1]);
}
