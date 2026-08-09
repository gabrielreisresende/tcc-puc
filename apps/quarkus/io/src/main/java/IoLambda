import com.amazonaws.services.lambda.runtime.Context;
import com.amazonaws.services.lambda.runtime.RequestHandler;
import jakarta.inject.Inject;
import software.amazon.awssdk.services.dynamodb.DynamoDbClient;
import software.amazon.awssdk.services.dynamodb.model.AttributeValue;
import software.amazon.awssdk.services.dynamodb.model.GetItemRequest;
import software.amazon.awssdk.services.dynamodb.model.PutItemRequest;
import java.time.Instant;
import java.util.Map;
import java.util.UUID;

public class IoLambda implements RequestHandler<Object, IoLambda.Response> {

    @Inject
    DynamoDbClient dynamoDB;

    public static class Response {
        public String message;
        public String itemId;
        public Response(String message, String itemId) { 
            this.message = message; 
            this.itemId = itemId;
        }
    }

    @Override
    public Response handleRequest(Object input, Context context) {
        String tableName = System.getenv("DYNAMODB_TABLE_NAME");
        String id = UUID.randomUUID().toString();

        Map<String, AttributeValue> item = Map.of(
            "id", AttributeValue.builder().s(id).build(),
            "timestamp", AttributeValue.builder().s(Instant.now().toString()).build(),
            "data", AttributeValue.builder().s("benchmark-io-test-quarkus").build()
        );

        // 1. Escrita
        dynamoDB.putItem(PutItemRequest.builder()
                .tableName(tableName)
                .item(item)
                .build());

        // 2. Leitura
        dynamoDB.getItem(GetItemRequest.builder()
                .tableName(tableName)
                .key(Map.of("id", AttributeValue.builder().s(id).build()))
                .build());

        return new Response("I/O operation successful", id);
    }
}