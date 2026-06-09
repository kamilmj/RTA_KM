from sklearn.linear_model import LinearRegression #dodane
from pyspark.sql import SparkSession
from pyspark.sql.functions import col, from_json, when
from pyspark.sql.types import StructType, StringType, FloatType, BooleanType
import sqlite3

spark = SparkSession.builder \
    .appName("FlightMonitor") \
    .config("spark.jars.packages", "org.apache.spark:spark-sql-kafka-0-10_2.13:4.0.0-preview2") \
    .getOrCreate()

spark.sparkContext.setLogLevel("WARN")

schema = StructType() \
    .add("icao24", StringType()) \
    .add("callsign", StringType()) \
    .add("origin_country", StringType()) \
    .add("longitude", FloatType()) \
    .add("latitude", FloatType()) \
    .add("altitude", FloatType()) \
    .add("on_ground", BooleanType()) \
    .add("velocity", FloatType()) \
    .add("vertical_rate", FloatType())

df = spark.readStream \
    .format("kafka") \
    .option("kafka.bootstrap.servers", "broker:9092") \
    .option("subscribe", "raw-adsb") \
    .load()

parsed_df = df.select(from_json(col("value").cast("string"), schema).alias("data")).select("data.*")

# Reguły 
processed_df = parsed_df.withColumn(
    "is_military_takeoff", # ta militarna reguła musiała by być bardziej wyrafinowana
    when((col("callsign").startswith("NATO") | (col("origin_country") == "United States")) & 
         (col("altitude") < 1500) & (col("vertical_rate") > 0) & (col("on_ground") == False), True).otherwise(False)
).withColumn(
    "is_overspeed",
    when((col("altitude") < 3000) & (col("velocity") > 130), True).otherwise(False)
)

def write_to_sqlite(batch_df, batch_id):
    pdf = batch_df.toPandas() #if else pod tym dodany
    if len(pdf) > 5:
        X = pdf[["altitude"]].fillna(0)
        y = pdf[["velocity"]].fillna(0)
        model = LinearRegression()
        model.fit(X, y)
        pdf["velocity_pred"] = model.predict(X)
    else:
        pdf["velocity_pred"] = 0
    if not pdf.empty:
        conn = sqlite3.connect('flights.db')
        pdf.to_sql('live_flights', conn, if_exists='replace', index=False)
        
        alerts_pdf = pdf[(pdf['is_military_takeoff'] == True) | (pdf['is_overspeed'] == True)]
        if not alerts_pdf.empty:
            alerts_pdf.to_sql('alerts_log', conn, if_exists='append', index=False)
        conn.close()

query = processed_df.writeStream \
    .foreachBatch(write_to_sqlite) \
    .outputMode("update") \
    .start()

query.awaitTermination()