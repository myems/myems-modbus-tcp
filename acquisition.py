import json
import mysql.connector
import time
import math
from datetime import datetime
import telnetlib
from modbus_tk import modbus_tcp
import config
from decimal import Decimal
from byte_swap import byte_swap_32_bit, byte_swap_64_bit


########################################################################################################################
# Acquisition Procedures
# Step 1: telnet hosts
# Step 2: Get point list
# Step 3: Read point values from Modbus slaves
# Step 4: Bulk insert point values and update latest values in historical database
########################################################################################################################


def process(logger, data_source_id, host, port):

    while True:
        # the outermost while loop

        ################################################################################################################
        # Step 1: telnet hosts
        ################################################################################################################
        try:
            telnetlib.Telnet(host, port, 10)
            print("Succeeded to telnet %s:%s in acquisition process ", host, port)
        except Exception as e:
            logger.error("Failed to telnet %s:%s in acquisition process: %s  ", host, port, str(e))
            time.sleep(300)
            continue

        ################################################################################################################
        # Step 2: Get point list
        ################################################################################################################
        cnx_system_db = None
        cursor_system_db = None
        try:
            cnx_system_db = mysql.connector.connect(**config.myems_system_db)
            cursor_system_db = cnx_system_db.cursor()
        except Exception as e:
            logger.error("Error in step 2.1 of acquisition process " + str(e))
            if cursor_system_db:
                cursor_system_db.close()
            if cnx_system_db:
                cnx_system_db.close()
            # sleep and then continue the outermost loop to reload points
            time.sleep(60)
            continue

        try:
            query = (" SELECT id, name, object_type, is_trend, ratio, address "
                     " FROM tbl_points "
                     " WHERE data_source_id = %s "
                     " ORDER BY id ")
            cursor_system_db.execute(query, (data_source_id, ))
            rows_point = cursor_system_db.fetchall()
        except Exception as e:
            logger.error("Error in step 2.2 of acquisition process: " + str(e))
            # sleep several minutes and continue the outer loop to reload points
            time.sleep(60)
            continue
        finally:
            if cursor_system_db:
                cursor_system_db.close()
            if cnx_system_db:
                cnx_system_db.close()

        if rows_point is None or len(rows_point) == 0:
            # there is no points for this data source
            logger.error("Point Not Found in Data Source (ID = %s), acquisition process terminated ", data_source_id)
            # sleep 60 seconds and go back to the begin of outermost while loop to reload points
            time.sleep(60)
            continue

        # There are points for this data source
        point_list = list()
        for row_point in rows_point:
            point_list.append({"id": row_point[0],
                               "name": row_point[1],
                               "object_type": row_point[2],
                               "is_trend": row_point[3],
                               "ratio": row_point[4],
                               "address": row_point[5]})

        ################################################################################################################
        # Step 3: Read point values from Modbus slaves
        ################################################################################################################
        # connect to historical database
        cnx_historical_db = None
        cursor_historical_db = None
        try:
            cnx_historical_db = mysql.connector.connect(**config.myems_historical_db)
            cursor_historical_db = cnx_historical_db.cursor()
        except Exception as e:
            logger.error("Error in step 3.1 of acquisition process " + str(e))
            if cursor_historical_db:
                cursor_historical_db.close()
            if cnx_historical_db:
                cnx_historical_db.close()
            # sleep 60 seconds and go back to the begin of outermost while loop to reload points
            time.sleep(60)
            continue

        # connect to the Modbus data source
        master = modbus_tcp.TcpMaster(host=host, port=port, timeout_in_sec=5.0)
        master.set_timeout(5.0)
        print("Ready to connect to %s:%s ", host, port)

        # inner loop to read all point values within a configurable period
        while True:
            is_modbus_tcp_timed_out = False
            energy_value_list = list()
            analog_value_list = list()
            digital_value_list = list()

            # foreach point loop
            for point in point_list:
                try:
                    address = json.loads(point['address'])
                except Exception as e:
                    logger.error("Error in step 3.2 of acquisition process: \n"
                                 "Invalid point address in JSON " + str(e))
                    continue

                if 'slave_id' not in address.keys() \
                    or 'function_code' not in address.keys() \
                    or 'offset' not in address.keys() \
                    or 'number_of_registers' not in address.keys() \
                    or 'format' not in address.keys() \
                    or 'byte_swap' not in address.keys() \
                    or address['slave_id'] < 1 \
                    or address['function_code'] not in (1, 2, 3, 4) \
                    or address['offset'] < 0 \
                    or address['number_of_registers'] < 0 \
                    or len(address['format']) < 1 \
                        or not isinstance(address['byte_swap'], bool):

                    logger.error('Data Source(ID=%s), Point(ID=%s) Invalid address data.',
                                 data_source_id, point['id'])
                    # invalid point is found, and go on the foreach point loop to process next point
                    continue

                # read register value for valid point
                try:
                    result = master.execute(slave=address['slave_id'],
                                            function_code=address['function_code'],
                                            starting_address=address['offset'],
                                            quantity_of_x=address['number_of_registers'],
                                            data_format=address['format'])
                except Exception as e:
                    logger.error(str(e) +
                                 " host:" + host + " port:" + str(port) +
                                 " slave_id:" + str(address['slave_id']) +
                                 " function_code:" + str(address['function_code']) +
                                 " starting_address:" + str(address['offset']) +
                                 " quantity_of_x:" + str(address['number_of_registers']) +
                                 " data_format:" + str(address['format']) +
                                 " byte_swap:" + str(address['byte_swap']))

                    if 'timed out' in str(e):
                        is_modbus_tcp_timed_out = True
                        # timeout error, break the foreach point loop
                        break
                    else:
                        # exception occurred when read register value, go on the foreach point loop
                        continue

                if result is None or not isinstance(result, tuple) or len(result) == 0:
                    # invalid result, and go on the foreach point loop to process next point
                    logger.error("Error in step 3.3 of acquisition process: \n"
                                 " invalid result: None "
                                 " for point_id: " + str(point['id']))
                    continue

                if not isinstance(result[0], float) and not isinstance(result[0], int) or math.isnan(result[0]):
                    # invalid result, and go on the foreach point loop to process next point
                    logger.error(" Error in step 3.4 of acquisition process:\n"
                                 " invalid result: not float and not int or not a number "
                                 " for point_id: " + str(point['id']))
                    continue

                if address['byte_swap']:
                    if address['number_of_registers'] == 2:
                        value = byte_swap_32_bit(result[0])
                    elif address['number_of_registers'] == 4:
                        value = byte_swap_64_bit(result[0])
                    else:
                        value = result[0]
                else:
                    value = result[0]

                if point['object_type'] == 'ANALOG_VALUE':
                    analog_value_list.append({'data_source_id': data_source_id,
                                              'point_id': point['id'],
                                              'is_trend': point['is_trend'],
                                              'value': Decimal(value) * point['ratio']})
                elif point['object_type'] == 'ENERGY_VALUE':
                    energy_value_list.append({'data_source_id': data_source_id,
                                              'point_id': point['id'],
                                              'is_trend': point['is_trend'],
                                              'value': Decimal(value) * point['ratio']})
                elif point['object_type'] == 'DIGITAL_VALUE':
                    digital_value_list.append({'data_source_id': data_source_id,
                                               'point_id': point['id'],
                                               'is_trend': point['is_trend'],
                                               'value': int(value) * int(point['ratio'])})

            # end of foreach point loop

            if is_modbus_tcp_timed_out:
                # Modbus TCP connection timeout error

                # destroy the Modbus master
                del master

                # close the connection to database
                if cursor_historical_db:
                    cursor_historical_db.close()
                if cnx_historical_db:
                    cnx_historical_db.close()

                # break the inner while loop to reconnect the Modbus device
                time.sleep(60)
                break

            ############################################################################################################
            # Step 4: Bulk insert point values and update latest values in historical database
            ############################################################################################################
            # check the connection to the Historical Database
            if not cnx_historical_db.is_connected():
                try:
                    cnx_historical_db = mysql.connector.connect(**config.myems_historical_db)
                    cursor_historical_db = cnx_historical_db.cursor()
                except Exception as e:
                    logger.error("Error in step 4.1 of acquisition process: " + str(e))
                    if cursor_historical_db:
                        cursor_historical_db.close()
                    if cnx_historical_db:
                        cnx_historical_db.close()
                    # sleep some seconds
                    time.sleep(60)
                    continue

            current_datetime_utc = datetime.utcnow()
            # bulk insert values into historical database within a period
            # update latest values in the meanwhile
            if len(analog_value_list) > 0:
                add_values = (" INSERT INTO tbl_analog_value (point_id, utc_date_time, actual_value) "
                              " VALUES  ")
                trend_value_count = 0

                for point_value in analog_value_list:
                    if point_value['is_trend']:
                        add_values += " (" + str(point_value['point_id']) + ","
                        add_values += "'" + current_datetime_utc.isoformat() + "',"
                        add_values += str(point_value['value']) + "), "
                        trend_value_count += 1

                if trend_value_count > 0:
                    try:
                        # trim ", " at the end of string and then execute
                        cursor_historical_db.execute(add_values[:-2])
                        cnx_historical_db.commit()
                    except Exception as e:
                        logger.error("Error in step 4.2.1 of acquisition process " + str(e))
                        # ignore this exception
                        pass

                # update tbl_analog_value_latest
                delete_values = " DELETE FROM tbl_analog_value_latest WHERE point_id IN ( "
                latest_values = (" INSERT INTO tbl_analog_value_latest (point_id, utc_date_time, actual_value) "
                                 " VALUES  ")
                latest_value_count = 0

                for point_value in analog_value_list:
                    delete_values += str(point_value['point_id']) + ","
                    latest_values += " (" + str(point_value['point_id']) + ","
                    latest_values += "'" + current_datetime_utc.isoformat() + "',"
                    latest_values += str(point_value['value']) + "), "
                    latest_value_count += 1

                if latest_value_count > 0:
                    try:
                        # replace "," at the end of string with ")"
                        cursor_historical_db.execute(delete_values[:-1] + ")")
                        cnx_historical_db.commit()
                    except Exception as e:
                        logger.error("Error in step 4.2.2 of acquisition process " + str(e))
                        # ignore this exception
                        pass

                    try:
                        # trim ", " at the end of string and then execute
                        cursor_historical_db.execute(latest_values[:-2])
                        cnx_historical_db.commit()
                    except Exception as e:
                        logger.error("Error in step 4.2.3 of acquisition process " + str(e))
                        # ignore this exception
                        pass

            if len(energy_value_list) > 0:
                add_values = (" INSERT INTO tbl_energy_value (point_id, utc_date_time, actual_value) "
                              " VALUES  ")
                trend_value_count = 0

                for point_value in energy_value_list:
                    if point_value['is_trend']:
                        add_values += " (" + str(point_value['point_id']) + ","
                        add_values += "'" + current_datetime_utc.isoformat() + "',"
                        add_values += str(point_value['value']) + "), "
                        trend_value_count += 1

                if trend_value_count > 0:
                    try:
                        # trim ", " at the end of string and then execute
                        cursor_historical_db.execute(add_values[:-2])
                        cnx_historical_db.commit()
                    except Exception as e:
                        logger.error("Error in step 4.3.1 of acquisition process: " + str(e))
                        # ignore this exception
                        pass

                # update tbl_energy_value_latest
                delete_values = " DELETE FROM tbl_energy_value_latest WHERE point_id IN ( "
                latest_values = (" INSERT INTO tbl_energy_value_latest (point_id, utc_date_time, actual_value) "
                                 " VALUES  ")

                latest_value_count = 0
                for point_value in energy_value_list:
                    delete_values += str(point_value['point_id']) + ","
                    latest_values += " (" + str(point_value['point_id']) + ","
                    latest_values += "'" + current_datetime_utc.isoformat() + "',"
                    latest_values += str(point_value['value']) + "), "
                    latest_value_count += 1

                if latest_value_count > 0:
                    try:
                        # replace "," at the end of string with ")"
                        cursor_historical_db.execute(delete_values[:-1] + ")")
                        cnx_historical_db.commit()

                    except Exception as e:
                        logger.error("Error in step 4.3.2 of acquisition process " + str(e))
                        # ignore this exception
                        pass

                    try:
                        # trim ", " at the end of string and then execute
                        cursor_historical_db.execute(latest_values[:-2])
                        cnx_historical_db.commit()

                    except Exception as e:
                        logger.error("Error in step 4.3.3 of acquisition process " + str(e))
                        # ignore this exception
                        pass

            if len(digital_value_list) > 0:
                add_values = (" INSERT INTO tbl_digital_value (point_id, utc_date_time, actual_value) "
                              " VALUES  ")
                trend_value_count = 0

                for point_value in digital_value_list:
                    if point_value['is_trend']:
                        add_values += " (" + str(point_value['point_id']) + ","
                        add_values += "'" + current_datetime_utc.isoformat() + "',"
                        add_values += str(point_value['value']) + "), "
                        trend_value_count += 1

                if trend_value_count > 0:
                    try:
                        # trim ", " at the end of string and then execute
                        cursor_historical_db.execute(add_values[:-2])
                        cnx_historical_db.commit()
                    except Exception as e:
                        logger.error("Error in step 4.4.1 of acquisition process: " + str(e))
                        # ignore this exception
                        pass

                # update tbl_digital_value_latest
                delete_values = " DELETE FROM tbl_digital_value_latest WHERE point_id IN ( "
                latest_values = (" INSERT INTO tbl_digital_value_latest (point_id, utc_date_time, actual_value) "
                                 " VALUES  ")
                latest_value_count = 0
                for point_value in digital_value_list:
                    delete_values += str(point_value['point_id']) + ","
                    latest_values += " (" + str(point_value['point_id']) + ","
                    latest_values += "'" + current_datetime_utc.isoformat() + "',"
                    latest_values += str(point_value['value']) + "), "
                    latest_value_count += 1

                if latest_value_count > 0:
                    try:
                        # replace "," at the end of string with ")"
                        cursor_historical_db.execute(delete_values[:-1] + ")")
                        cnx_historical_db.commit()
                    except Exception as e:
                        logger.error("Error in step 4.4.2 of acquisition process " + str(e))
                        # ignore this exception
                        pass

                    try:
                        # trim ", " at the end of string and then execute
                        cursor_historical_db.execute(latest_values[:-2])
                        cnx_historical_db.commit()
                    except Exception as e:
                        logger.error("Error in step 4.4.3 of acquisition process " + str(e))
                        # ignore this exception
                        pass

            # sleep some seconds
            time.sleep(config.interval_in_seconds)

        # end of inner while loop

    # end of outermost while loop
