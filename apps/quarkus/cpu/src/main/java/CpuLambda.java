import com.amazonaws.services.lambda.runtime.Context;
import com.amazonaws.services.lambda.runtime.RequestHandler;
import java.util.ArrayList;
import java.util.List;

public class CpuLambda implements RequestHandler<CpuLambda.Request, CpuLambda.Response> {

    public static class Request {
        public Long number;
    }

    public static class Response {
        public List<Long> factors;
        public Response(List<Long> factors) { this.factors = factors; }
    }

    @Override
    public Response handleRequest(Request request, Context context) {
        long num = (request.number != null && request.number > 1) ? request.number : 999999999989L;
        return new Response(primeFactors(num));
    }

    private List<Long> primeFactors(long n) {
        List<Long> factors = new ArrayList<>();
        while (n % 2 == 0) {
            factors.add(2L);
            n /= 2;
        }
        for (long i = 3; i <= Math.sqrt(n); i += 2) {
            while (n % i == 0) {
                factors.add(i);
                n /= i;
            }
        }
        if (n > 2) factors.add(n);
        return factors;
    }
}