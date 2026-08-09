import com.amazonaws.services.lambda.runtime.Context;
import com.amazonaws.services.lambda.runtime.RequestHandler;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

public class ConcurrencyLambda implements RequestHandler<ConcurrencyLambda.Request, ConcurrencyLambda.Response> {

    public static class Request {
        public Integer tasks;
    }

    public static class Response {
        public int completedTasks;
        public Response(int completedTasks) { this.completedTasks = completedTasks; }
    }

    @Override
    public Response handleRequest(Request request, Context context) {
        int numTasks = (request.tasks != null && request.tasks > 0) ? request.tasks : 5000;
        AtomicInteger counter = new AtomicInteger(0);

        // Executor baseado em Virtual Threads (Java 21+)
        try (ExecutorService executor = Executors.newVirtualThreadPerTaskExecutor()) {
            for (int i = 0; i < numTasks; i++) {
                executor.submit(() -> {
                    double calc = 0.0;
                    for (int j = 0; j < 1000; j++) {
                        calc += 1.0;
                    }
                    counter.incrementAndGet();
                });
            }
            executor.shutdown();
            executor.awaitTermination(30, TimeUnit.SECONDS);
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
        }

        return new Response(counter.get());
    }
}