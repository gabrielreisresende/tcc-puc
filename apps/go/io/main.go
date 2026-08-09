package main

import (
	"context"
	"fmt"
	"os"
	"time"

	"github.com/aws/aws-lambda-go/lambda"
	"github.com/aws/aws-sdk-go-v2/config"
	"github.com/aws/aws-sdk-go-v2/feature/dynamodb/attributevalue"
	"github.com/aws/aws-sdk-go-v2/service/dynamodb"
	"github.com/google/uuid"
)

type Item struct {
	ID        string `json:"id" dynamodbav:"id"`
	Timestamp string `json:"timestamp" dynamodbav:"timestamp"`
	Data      string `json:"data" dynamodbav:"data"`
}

type Response struct {
	Message string `json:"message"`
	ItemID  string `json:"item_id"`
}

var dbClient *dynamodb.Client
var tableName string

func init() {
	tableName = os.Getenv("DYNAMODB_TABLE_NAME")
	cfg, err := config.LoadDefaultConfig(context.TODO())
	if err == nil {
		dbClient = dynamodb.NewFromConfig(cfg)
	}
}

func handler(ctx context.Context) (Response, error) {
	if dbClient == nil {
		return Response{}, fmt.Errorf("dynamodb client not initialized")
	}

	item := Item{
		ID:        uuid.New().String(),
		Timestamp: time.Now().Format(time.RFC3339),
		Data:      "benchmark-io-test-go",
	}

	av, err := attributevalue.MarshalMap(item)
	if err != nil {
		return Response{}, err
	}

	// 1. Escrita
	_, err = dbClient.PutItem(ctx, &dynamodb.PutItemInput{
		TableName: &tableName,
		Item:      av,
	})
	if err != nil {
		return Response{}, err
	}

	// 2. Leitura
	key, _ := attributevalue.MarshalMap(map[string]string{"id": item.ID})
	_, err = dbClient.GetItem(ctx, &dynamodb.GetItemInput{
		TableName: &tableName,
		Key:       key,
	})
	if err != nil {
		return Response{}, err
	}

	return Response{Message: "I/O operation successful", ItemID: item.ID}, nil
}

func main() {
	lambda.Start(handler)
}
