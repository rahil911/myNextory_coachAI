/*M!999999\- enable the sandbox mode */ 
-- MariaDB dump 10.19  Distrib 10.11.14-MariaDB, for debian-linux-gnu (x86_64)
--
-- Host: localhost    Database: baap
-- ------------------------------------------------------
-- Server version	10.11.14-MariaDB-0ubuntu0.24.04.1

/*!40101 SET @OLD_CHARACTER_SET_CLIENT=@@CHARACTER_SET_CLIENT */;
/*!40101 SET @OLD_CHARACTER_SET_RESULTS=@@CHARACTER_SET_RESULTS */;
/*!40101 SET @OLD_COLLATION_CONNECTION=@@COLLATION_CONNECTION */;
/*!40101 SET NAMES utf8mb4 */;
/*!40103 SET @OLD_TIME_ZONE=@@TIME_ZONE */;
/*!40103 SET TIME_ZONE='+00:00' */;
/*!40014 SET @OLD_UNIQUE_CHECKS=@@UNIQUE_CHECKS, UNIQUE_CHECKS=0 */;
/*!40014 SET @OLD_FOREIGN_KEY_CHECKS=@@FOREIGN_KEY_CHECKS, FOREIGN_KEY_CHECKS=0 */;
/*!40101 SET @OLD_SQL_MODE=@@SQL_MODE, SQL_MODE='NO_AUTO_VALUE_ON_ZERO' */;
/*!40111 SET @OLD_SQL_NOTES=@@SQL_NOTES, SQL_NOTES=0 */;

--
-- Table structure for table `activity_log`
--

DROP TABLE IF EXISTS `activity_log`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `activity_log` (
  `id` bigint(20) NOT NULL AUTO_INCREMENT,
  `log_name` varchar(255) DEFAULT NULL,
  `description` longtext NOT NULL,
  `subject_type` varchar(255) DEFAULT NULL,
  `subject_id` bigint(20) DEFAULT NULL,
  `causer_type` varchar(255) DEFAULT NULL,
  `causer_id` bigint(20) DEFAULT NULL,
  `properties` longtext DEFAULT NULL,
  `created_at` datetime DEFAULT NULL,
  `updated_at` datetime DEFAULT NULL,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=70875 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `backpacks`
--

DROP TABLE IF EXISTS `backpacks`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `backpacks` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `nx_journey_detail_id` int(11) DEFAULT NULL,
  `nx_chapter_detail_id` int(11) DEFAULT NULL,
  `nx_lesson_id` int(11) DEFAULT NULL,
  `lesson_detail_id` int(11) DEFAULT NULL,
  `lesson_slide_id` int(11) DEFAULT NULL,
  `form_type` varchar(50) DEFAULT NULL,
  `data` longtext DEFAULT NULL,
  `created_by` int(11) DEFAULT NULL,
  `user_type` varchar(20) DEFAULT NULL,
  `created_at` datetime DEFAULT NULL,
  `updated_at` datetime DEFAULT NULL,
  `deleted_at` datetime DEFAULT NULL,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=12068 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `chatbot_documents`
--

DROP TABLE IF EXISTS `chatbot_documents`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `chatbot_documents` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `pdf` longtext DEFAULT NULL,
  `created_at` datetime DEFAULT NULL,
  `updated_at` datetime DEFAULT NULL,
  `deleted_at` datetime DEFAULT NULL,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=107 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `chatbot_histories`
--

DROP TABLE IF EXISTS `chatbot_histories`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `chatbot_histories` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `user_type` varchar(20) DEFAULT NULL,
  `created_by` int(11) DEFAULT NULL,
  `question` longtext DEFAULT NULL,
  `question_time` datetime DEFAULT NULL,
  `answer` longtext DEFAULT NULL,
  `answer_time` datetime DEFAULT NULL,
  `is_global_chat` tinyint(1) DEFAULT NULL,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=292 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `chatbot_sessions`
--

DROP TABLE IF EXISTS `chatbot_sessions`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `chatbot_sessions` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `user_type` varchar(20) DEFAULT NULL,
  `created_by` int(11) DEFAULT NULL,
  `session_data` longtext DEFAULT NULL,
  `created_at` datetime NOT NULL,
  `updated_at` datetime NOT NULL,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `client_coach_mappings`
--

DROP TABLE IF EXISTS `client_coach_mappings`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `client_coach_mappings` (
  `id` bigint(20) DEFAULT NULL,
  `client_id` bigint(20) DEFAULT NULL,
  `coach_id` bigint(20) DEFAULT NULL,
  `deleted_at` datetime DEFAULT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `client_password_resets`
--

DROP TABLE IF EXISTS `client_password_resets`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `client_password_resets` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `email` longtext DEFAULT NULL,
  `token` longtext DEFAULT NULL,
  `created_at` datetime DEFAULT NULL,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `clients`
--

DROP TABLE IF EXISTS `clients`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `clients` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `employer_id` varchar(50) DEFAULT NULL,
  `company_logo` varchar(100) DEFAULT NULL,
  `company_name` varchar(200) DEFAULT NULL,
  `address_1` longtext DEFAULT NULL,
  `address_2` longtext DEFAULT NULL,
  `city` longtext DEFAULT NULL,
  `state` varchar(40) DEFAULT NULL,
  `zipcode` varchar(5) DEFAULT NULL,
  `primary_name` varchar(200) DEFAULT NULL,
  `primary_phone_number` varchar(11) DEFAULT NULL,
  `primary_email` varchar(100) DEFAULT NULL,
  `secondary_name` varchar(200) DEFAULT NULL,
  `secondary_phone_number` varchar(11) DEFAULT NULL,
  `secondary_email` varchar(50) DEFAULT NULL,
  `password` longtext DEFAULT NULL,
  `is_password_reset` bigint(20) DEFAULT NULL,
  `remember_token` longtext DEFAULT NULL,
  `is_email_sent` tinyint(1) DEFAULT NULL,
  `status` varchar(30) DEFAULT NULL,
  `deleted_at` datetime DEFAULT NULL,
  `created_at` datetime DEFAULT NULL,
  `updated_at` datetime DEFAULT NULL,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=51 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `coach_availabilities`
--

DROP TABLE IF EXISTS `coach_availabilities`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `coach_availabilities` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `coach_id` int(11) DEFAULT NULL,
  `day` varchar(50) DEFAULT NULL,
  `session` varchar(50) DEFAULT NULL,
  `start_time` time(6) DEFAULT NULL,
  `end_time` time(6) DEFAULT NULL,
  `time_zone` varchar(50) DEFAULT NULL,
  `tot_hrs_per_week` varchar(50) DEFAULT NULL,
  `created_at` datetime DEFAULT NULL,
  `deleted_at` datetime DEFAULT NULL,
  `updated_at` datetime DEFAULT NULL,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=10 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `coach_password_resets`
--

DROP TABLE IF EXISTS `coach_password_resets`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `coach_password_resets` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `email` longtext DEFAULT NULL,
  `token` longtext DEFAULT NULL,
  `created_at` datetime DEFAULT NULL,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `coach_profiles`
--

DROP TABLE IF EXISTS `coach_profiles`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `coach_profiles` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `coach_id` int(11) DEFAULT NULL,
  `first_name` varchar(50) DEFAULT NULL,
  `last_name` varchar(50) DEFAULT NULL,
  `time_zone` varchar(50) DEFAULT NULL,
  `linkdin_url` longtext DEFAULT NULL,
  `mobile_no` bigint(20) DEFAULT NULL,
  `email` varchar(50) DEFAULT NULL,
  `bio_link` varchar(50) DEFAULT NULL,
  `payroll_link` varchar(50) DEFAULT NULL,
  `language` longtext DEFAULT NULL,
  `gender` varchar(20) DEFAULT NULL,
  `area_of_expertise` longtext DEFAULT NULL,
  `coaching_expertise` longtext DEFAULT NULL,
  `deleted_at` datetime DEFAULT NULL,
  `created_at` datetime DEFAULT NULL,
  `updated_at` datetime DEFAULT NULL,
  `profile` longtext DEFAULT NULL,
  `rating` int(11) DEFAULT NULL,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=8 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `coaches`
--

DROP TABLE IF EXISTS `coaches`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `coaches` (
  `id` bigint(20) NOT NULL AUTO_INCREMENT,
  `email` varchar(50) NOT NULL,
  `email_verified_at` varchar(80) DEFAULT NULL,
  `username` varchar(80) DEFAULT NULL,
  `password` varchar(80) NOT NULL,
  `verification_code` bigint(20) DEFAULT NULL,
  `verified_at` datetime DEFAULT NULL,
  `is_profile_done` int(11) DEFAULT NULL,
  `remember_token` longtext DEFAULT NULL,
  `deleted_at` datetime DEFAULT NULL,
  `created_at` datetime DEFAULT NULL,
  `updated_at` datetime DEFAULT NULL,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=9 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `departments`
--

DROP TABLE IF EXISTS `departments`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `departments` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `client_id` int(11) DEFAULT NULL,
  `department_title` varchar(100) DEFAULT NULL,
  `created_at` datetime DEFAULT NULL,
  `updated_at` datetime DEFAULT NULL,
  `deleted_at` datetime DEFAULT NULL,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=510 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `documents`
--

DROP TABLE IF EXISTS `documents`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `documents` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `document_title` longtext DEFAULT NULL,
  `description` longtext DEFAULT NULL,
  `url` longtext DEFAULT NULL,
  `tag` longtext DEFAULT NULL,
  `document_file` varchar(50) DEFAULT NULL,
  `created_at` datetime DEFAULT NULL,
  `updated_at` datetime DEFAULT NULL,
  `deleted_at` datetime DEFAULT NULL,
  `themes` longtext DEFAULT NULL,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=145 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `dynamic_sms_details`
--

DROP TABLE IF EXISTS `dynamic_sms_details`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `dynamic_sms_details` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `nx_chapter_detail_id` int(11) DEFAULT NULL,
  `nx_lesson_id` int(11) DEFAULT NULL,
  `lesson_detail_id` int(11) DEFAULT NULL,
  `lesson_slide_id` int(11) DEFAULT NULL,
  `diff_minutes` int(11) DEFAULT NULL,
  `no_of_days` varchar(50) DEFAULT NULL,
  `subject` longtext DEFAULT NULL,
  `message` longtext DEFAULT NULL,
  `message_type` varchar(50) DEFAULT NULL,
  `slide_type` varchar(50) DEFAULT NULL,
  `created_by` int(11) DEFAULT NULL,
  `user_type` varchar(50) DEFAULT NULL,
  `on_complete` int(11) DEFAULT NULL,
  `created_at` datetime DEFAULT NULL,
  `updated_at` datetime DEFAULT NULL,
  `deleted_at` datetime DEFAULT NULL,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=103 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `employees`
--

DROP TABLE IF EXISTS `employees`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `employees` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `nx_user_id` int(11) NOT NULL,
  `employee_id` varchar(50) NOT NULL,
  `first_name` varchar(200) NOT NULL,
  `last_name` varchar(200) NOT NULL,
  `nick_name` varchar(100) DEFAULT NULL,
  `dob` varchar(100) DEFAULT NULL,
  `func_report` varchar(100) DEFAULT NULL,
  `date_hired` date DEFAULT NULL,
  `department_id` bigint(20) DEFAULT NULL,
  `mobile_no` varchar(15) DEFAULT NULL,
  `address_1` longtext DEFAULT NULL,
  `address_2` longtext DEFAULT NULL,
  `state` varchar(50) DEFAULT NULL,
  `city` longtext DEFAULT NULL,
  `zipcode` varchar(8) DEFAULT NULL,
  `status` varchar(15) DEFAULT NULL,
  `supervisor_name` varchar(100) DEFAULT NULL,
  `supervisor_email_id` varchar(30) DEFAULT NULL,
  `sup_status` varchar(30) DEFAULT NULL,
  `supervisor_last_name` varchar(50) DEFAULT NULL,
  `gender` varchar(7) DEFAULT NULL,
  `supervisor_address1` longtext DEFAULT NULL,
  `supervisor_address2` longtext DEFAULT NULL,
  `home_city` longtext DEFAULT NULL,
  `home_state` varchar(50) DEFAULT NULL,
  `home_zipcode` varchar(8) DEFAULT NULL,
  `supervisor_link_url` varchar(200) DEFAULT NULL,
  `deleted_at` datetime DEFAULT NULL,
  `created_at` datetime DEFAULT NULL,
  `updated_at` datetime DEFAULT NULL,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=1630 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `jobs`
--

DROP TABLE IF EXISTS `jobs`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `jobs` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `client_id` int(11) DEFAULT NULL,
  `job_title` varchar(100) DEFAULT NULL,
  `updated_at` datetime DEFAULT NULL,
  `created_at` datetime DEFAULT NULL,
  `deleted_at` datetime DEFAULT NULL,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `lesson_details`
--

DROP TABLE IF EXISTS `lesson_details`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `lesson_details` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `nx_journey_detail_id` int(11) DEFAULT NULL,
  `nx_chapter_detail_id` int(11) DEFAULT NULL,
  `nx_lesson_id` int(11) DEFAULT NULL,
  `created_by` int(11) DEFAULT NULL,
  `created_user_type` varchar(20) DEFAULT NULL,
  `status` varchar(20) DEFAULT NULL,
  `reason` longtext DEFAULT NULL,
  `created_at` datetime DEFAULT NULL,
  `updated_at` datetime DEFAULT NULL,
  `deleted_at` datetime DEFAULT NULL,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=123 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `lesson_slides`
--

DROP TABLE IF EXISTS `lesson_slides`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `lesson_slides` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `lesson_detail_id` int(11) DEFAULT NULL,
  `type` varchar(50) DEFAULT NULL,
  `slide_content` longtext DEFAULT NULL,
  `video_library_id` int(11) DEFAULT NULL,
  `priority` int(11) DEFAULT NULL,
  `created_at` datetime DEFAULT NULL,
  `updated_at` datetime DEFAULT NULL,
  `deleted_at` datetime DEFAULT NULL,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=919 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `mail_communication_details`
--

DROP TABLE IF EXISTS `mail_communication_details`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `mail_communication_details` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `mail_communication_detail_id` int(11) DEFAULT NULL,
  `query_type` varchar(50) DEFAULT NULL,
  `subject` longtext DEFAULT NULL,
  `description` longtext DEFAULT NULL,
  `status` varchar(50) DEFAULT NULL,
  `attachment` longtext DEFAULT NULL,
  `from_type` varchar(10) DEFAULT NULL,
  `from_id` int(11) DEFAULT NULL,
  `is_transfered` int(11) DEFAULT NULL,
  `created_at` datetime DEFAULT NULL,
  `updated_at` datetime DEFAULT NULL,
  `deleted_at` datetime DEFAULT NULL,
  `user_id` longtext DEFAULT NULL,
  `coach_id` longtext DEFAULT NULL,
  `client_id` longtext DEFAULT NULL,
  `admin_user_id` longtext DEFAULT NULL,
  `support` varchar(50) DEFAULT NULL,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=46 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `mail_transfers`
--

DROP TABLE IF EXISTS `mail_transfers`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `mail_transfers` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `mail_communication_detail_id` int(11) DEFAULT NULL,
  `from_type` varchar(20) DEFAULT NULL,
  `from_id` bigint(20) DEFAULT NULL,
  `to_type` varchar(20) DEFAULT NULL,
  `to_id` bigint(20) DEFAULT NULL,
  `comments` longtext DEFAULT NULL,
  `created_at` datetime DEFAULT NULL,
  `updated_at` datetime DEFAULT NULL,
  `deleted_at` datetime DEFAULT NULL,
  `is_transfered` int(11) DEFAULT NULL,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `meeting_attendees`
--

DROP TABLE IF EXISTS `meeting_attendees`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `meeting_attendees` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `meeting_id` bigint(20) DEFAULT NULL,
  `user_type` varchar(50) DEFAULT NULL,
  `participant_id` int(11) DEFAULT NULL,
  `join_time` datetime DEFAULT NULL,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `meetings`
--

DROP TABLE IF EXISTS `meetings`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `meetings` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `title` longtext DEFAULT NULL,
  `DATE` date DEFAULT NULL,
  `from_time` time(6) DEFAULT NULL,
  `to_time` time(6) DEFAULT NULL,
  `description` longtext DEFAULT NULL,
  `type` varchar(30) DEFAULT NULL,
  `hosting_by` int(11) DEFAULT NULL,
  `user_id` longtext DEFAULT NULL,
  `meeting_id` longtext DEFAULT NULL,
  `password` varchar(50) DEFAULT NULL,
  `created_at` datetime DEFAULT NULL,
  `updated_at` datetime DEFAULT NULL,
  `deleted_at` datetime DEFAULT NULL,
  `client_id` longtext DEFAULT NULL,
  `coach_id` longtext DEFAULT NULL,
  `admin_id` longtext DEFAULT NULL,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `notification_histories`
--

DROP TABLE IF EXISTS `notification_histories`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `notification_histories` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `nx_user_id` int(11) DEFAULT NULL,
  `notification_from` varchar(100) DEFAULT NULL,
  `notification_table_id` int(11) DEFAULT NULL,
  `created_at` datetime DEFAULT NULL,
  `coach_id` bigint(20) DEFAULT NULL,
  `client_id` bigint(20) DEFAULT NULL,
  `admin_user_id` bigint(20) DEFAULT NULL,
  `read_at` datetime DEFAULT NULL,
  `unread_at` datetime DEFAULT NULL,
  `deleted_at` datetime DEFAULT NULL,
  `status` smallint(6) DEFAULT NULL,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=95 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `nx_admin_users`
--

DROP TABLE IF EXISTS `nx_admin_users`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `nx_admin_users` (
  `id` bigint(20) NOT NULL AUTO_INCREMENT,
  `mobile_no` bigint(20) DEFAULT NULL,
  `email` varchar(50) NOT NULL,
  `email_verified_at` varchar(80) DEFAULT NULL,
  `username` varchar(80) DEFAULT NULL,
  `password` varchar(80) NOT NULL,
  `verification_code` bigint(20) DEFAULT NULL,
  `verified_at` datetime DEFAULT NULL,
  `is_profile_done` int(11) DEFAULT NULL,
  `remember_token` varchar(200) DEFAULT NULL,
  `deleted_at` datetime DEFAULT NULL,
  `created_at` datetime DEFAULT NULL,
  `updated_at` datetime DEFAULT NULL,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=2 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `nx_chapter_details`
--

DROP TABLE IF EXISTS `nx_chapter_details`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `nx_chapter_details` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `nx_journey_detail_id` int(11) DEFAULT NULL,
  `chapter` longtext DEFAULT NULL,
  `description` longtext DEFAULT NULL,
  `no_of_lessons` int(11) DEFAULT NULL,
  `no_of_total_hrs` time(6) DEFAULT NULL,
  `icon` longtext DEFAULT NULL,
  `total_slides` int(11) DEFAULT NULL,
  `created_at` datetime DEFAULT NULL,
  `orders` int(11) DEFAULT NULL,
  `is_recomended` int(11) DEFAULT NULL,
  `has_sublesson` int(11) DEFAULT NULL,
  `created_by` int(11) DEFAULT NULL,
  `created_user_type` longtext DEFAULT NULL,
  `updated_at` datetime DEFAULT NULL,
  `deleted_at` datetime DEFAULT NULL,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=74 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `nx_journal_details`
--

DROP TABLE IF EXISTS `nx_journal_details`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `nx_journal_details` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `nx_user_id` int(11) DEFAULT NULL,
  `nx_journey_detail_id` int(11) DEFAULT NULL,
  `nx_chapter_detail_id` int(11) DEFAULT NULL,
  `nx_lesson_id` int(11) DEFAULT NULL,
  `nx_lesson_detail_id` varchar(50) DEFAULT NULL,
  `nx_lesson_slide_id` varchar(50) DEFAULT NULL,
  `url` varchar(250) DEFAULT NULL,
  `page` varchar(250) DEFAULT NULL,
  `journal_detail` longtext DEFAULT NULL,
  `deleted_at` datetime DEFAULT NULL,
  `created_at` datetime DEFAULT NULL,
  `updated_at` datetime DEFAULT NULL,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=113 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `nx_journey_details`
--

DROP TABLE IF EXISTS `nx_journey_details`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `nx_journey_details` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `journey` longtext DEFAULT NULL,
  `journey_description` longtext DEFAULT NULL,
  `no_of_chapters` varchar(50) DEFAULT NULL,
  `icon` varchar(50) DEFAULT NULL,
  `created_by` int(11) DEFAULT NULL,
  `created_user_type` varchar(50) DEFAULT NULL,
  `created_at` datetime DEFAULT NULL,
  `updated_at` datetime DEFAULT NULL,
  `deleted_at` datetime DEFAULT NULL,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=22 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `nx_lessons`
--

DROP TABLE IF EXISTS `nx_lessons`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `nx_lessons` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `nx_journey_detail_id` int(11) DEFAULT NULL,
  `nx_chapter_detail_id` int(11) DEFAULT NULL,
  `lesson` longtext DEFAULT NULL,
  `no_of_sublessons` int(11) DEFAULT NULL,
  `total_hrs` time(6) DEFAULT NULL,
  `description` longtext DEFAULT NULL,
  `is_foundation` int(11) DEFAULT NULL,
  `route_name` longtext DEFAULT NULL,
  `is_sublesson` int(11) DEFAULT NULL,
  `priority` int(11) DEFAULT NULL,
  `created_by` int(11) DEFAULT NULL,
  `created_user_type` longtext DEFAULT NULL,
  `created_at` datetime DEFAULT NULL,
  `updated_at` datetime DEFAULT NULL,
  `deleted_at` datetime DEFAULT NULL,
  `old_lesson_id` int(11) DEFAULT NULL,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=120 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `nx_password_resets`
--

DROP TABLE IF EXISTS `nx_password_resets`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `nx_password_resets` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `email` longtext DEFAULT NULL,
  `token` longtext DEFAULT NULL,
  `created_at` datetime DEFAULT NULL,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=872 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `nx_user_onboardings`
--

DROP TABLE IF EXISTS `nx_user_onboardings`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `nx_user_onboardings` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `nx_user_id` int(11) DEFAULT NULL,
  `first_name` varchar(80) DEFAULT NULL,
  `last_name` varchar(80) DEFAULT NULL,
  `address1` longtext DEFAULT NULL,
  `address2` longtext DEFAULT NULL,
  `city` varchar(50) DEFAULT NULL,
  `state` varchar(50) DEFAULT NULL,
  `mobile_no` varchar(11) DEFAULT NULL,
  `zipcode` varchar(5) DEFAULT NULL,
  `linkdin_url` longtext DEFAULT NULL,
  `gender` varchar(20) DEFAULT NULL,
  `why_did_you_come` longtext DEFAULT NULL,
  `own_reason` longtext DEFAULT NULL,
  `in_first_professional_job` varchar(5) DEFAULT NULL,
  `call_yourself` longtext DEFAULT NULL,
  `advance_your_career` longtext DEFAULT NULL,
  `imp_thing_career_plan` longtext DEFAULT NULL,
  `best_boss` longtext DEFAULT NULL,
  `success_look_like` longtext DEFAULT NULL,
  `stay_longer` varchar(10) DEFAULT NULL,
  `future_months` int(11) DEFAULT NULL,
  `profile` longtext DEFAULT NULL,
  `rating` int(11) DEFAULT NULL,
  `communication_type` varchar(10) DEFAULT NULL,
  `personal_email_id` longtext DEFAULT NULL,
  `assesment_order_id` longtext DEFAULT NULL,
  `assesment_request` longtext DEFAULT NULL,
  `assesment_response` longtext DEFAULT NULL,
  `assesment_result` longtext DEFAULT NULL,
  `created_at` datetime DEFAULT NULL,
  `updated_at` datetime DEFAULT NULL,
  `deleted_at` datetime DEFAULT NULL,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=578 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `nx_user_ratings`
--

DROP TABLE IF EXISTS `nx_user_ratings`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `nx_user_ratings` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `nx_journey_detail_id` int(11) DEFAULT NULL,
  `nx_chapter_detail_id` int(11) NOT NULL,
  `nx_lesson_id` int(11) DEFAULT NULL,
  `lesson_detail_id` int(11) DEFAULT NULL,
  `lesson_slide_id` int(11) DEFAULT NULL,
  `rating` int(11) DEFAULT NULL,
  `is_chapter_completed` int(11) DEFAULT NULL,
  `slide_index` int(11) DEFAULT NULL,
  `created_by` int(11) DEFAULT NULL,
  `user_type` varchar(50) DEFAULT NULL,
  `created_at` datetime DEFAULT NULL,
  `updated_at` datetime DEFAULT NULL,
  `deleted_at` datetime DEFAULT NULL,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=3435 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `nx_users`
--

DROP TABLE IF EXISTS `nx_users`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `nx_users` (
  `id` bigint(20) NOT NULL AUTO_INCREMENT,
  `email` varchar(50) NOT NULL,
  `email_verified_at` varchar(80) DEFAULT NULL,
  `secondary_email` varchar(50) DEFAULT NULL,
  `username` varchar(80) DEFAULT NULL,
  `password` varchar(80) NOT NULL,
  `verification_code` bigint(20) DEFAULT NULL,
  `verified_at` datetime DEFAULT NULL,
  `is_profile_done` int(11) DEFAULT NULL,
  `remember_token` longtext DEFAULT NULL,
  `deleted_at` datetime DEFAULT NULL,
  `created_at` datetime DEFAULT NULL,
  `updated_at` datetime DEFAULT NULL,
  `client_id` bigint(20) DEFAULT NULL,
  `is_password_reset` bigint(20) DEFAULT NULL,
  `is_email_sent` tinyint(1) DEFAULT NULL,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=4652 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `old_ratings`
--

DROP TABLE IF EXISTS `old_ratings`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `old_ratings` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `nx_user_id` int(11) DEFAULT NULL,
  `nx_journey_detail_id` int(11) DEFAULT NULL,
  `nx_chapter_detail_id` int(11) NOT NULL,
  `nx_lesson_id` int(11) DEFAULT NULL,
  `rating` int(11) DEFAULT NULL,
  `slide_index` int(11) DEFAULT NULL,
  `created_at` datetime DEFAULT NULL,
  `updated_at` datetime DEFAULT NULL,
  `deleted_at` datetime DEFAULT NULL,
  `nx_coach_id` bigint(20) DEFAULT NULL,
  `nx_admin_id` bigint(20) DEFAULT NULL,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=500 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `sms_details`
--

DROP TABLE IF EXISTS `sms_details`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `sms_details` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `nx_user_id` int(11) DEFAULT NULL,
  `nx_chapter_detail_id` int(11) DEFAULT NULL,
  `nx_lesson_id` int(11) DEFAULT NULL,
  `nx_user_backpack_detail_id` int(11) DEFAULT NULL,
  `message_when` int(11) DEFAULT NULL,
  `sms_type` longtext DEFAULT NULL,
  `mobile_number` char(100) DEFAULT NULL,
  `message` longtext DEFAULT NULL,
  `response` longtext DEFAULT NULL,
  `created_at` datetime DEFAULT NULL,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=5998 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `sms_schedules`
--

DROP TABLE IF EXISTS `sms_schedules`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `sms_schedules` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `sms_type` longtext DEFAULT NULL,
  `email_sms` varchar(10) DEFAULT NULL,
  `message_when` int(11) DEFAULT NULL,
  `message` longtext DEFAULT NULL,
  `form_type` longtext DEFAULT NULL,
  `nx_lesson_id` int(11) DEFAULT NULL,
  `nx_chapter_detail_id` int(11) DEFAULT NULL,
  `email_subject` varchar(100) DEFAULT NULL,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=31 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `tasks`
--

DROP TABLE IF EXISTS `tasks`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `tasks` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `user_type` varchar(30) DEFAULT NULL,
  `created_by` bigint(20) DEFAULT NULL,
  `nx_journey_detail_id` bigint(20) DEFAULT NULL,
  `nx_chapter_detail_id` bigint(20) DEFAULT NULL,
  `nx_lesson_id` bigint(20) DEFAULT NULL,
  `lesson_slide_id` int(11) DEFAULT NULL,
  `lesson_detail_id` int(11) DEFAULT NULL,
  `form_type` varchar(30) DEFAULT NULL,
  `title` longtext DEFAULT NULL,
  `data` longtext DEFAULT NULL,
  `status` varchar(20) DEFAULT NULL,
  `created_at` datetime DEFAULT NULL,
  `updated_at` datetime DEFAULT NULL,
  `deleted_at` datetime DEFAULT NULL,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=2929 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `tory_agent_sessions`
--

DROP TABLE IF EXISTS `tory_agent_sessions`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `tory_agent_sessions` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `nx_user_id` bigint(20) NOT NULL,
  `session_id` varchar(100) NOT NULL,
  `claude_session_id` varchar(200) DEFAULT NULL,
  `transcript_path` varchar(500) DEFAULT NULL,
  `status` varchar(20) DEFAULT 'running',
  `tool_call_count` int(11) DEFAULT 0,
  `error_message` text DEFAULT NULL,
  `pipeline_steps` longtext CHARACTER SET utf8mb4 COLLATE utf8mb4_bin DEFAULT NULL CHECK (json_valid(`pipeline_steps`)),
  `created_at` datetime DEFAULT current_timestamp(),
  `updated_at` datetime DEFAULT current_timestamp() ON UPDATE current_timestamp(),
  `deleted_at` datetime DEFAULT NULL,
  PRIMARY KEY (`id`),
  KEY `idx_user` (`nx_user_id`),
  KEY `idx_session` (`session_id`),
  KEY `idx_claude_session` (`claude_session_id`),
  KEY `idx_status` (`status`)
) ENGINE=InnoDB AUTO_INCREMENT=2 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `tory_ai_sessions`
--

DROP TABLE IF EXISTS `tory_ai_sessions`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `tory_ai_sessions` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `nx_user_id` int(11) NOT NULL,
  `role` enum('curator','companion','creator') NOT NULL,
  `initiated_by` int(11) DEFAULT NULL,
  `session_state` longblob DEFAULT NULL,
  `key_facts` longtext DEFAULT NULL,
  `message_count` int(11) DEFAULT 0,
  `model_tier` varchar(20) DEFAULT 'sonnet',
  `total_input_tokens` int(11) DEFAULT 0,
  `total_output_tokens` int(11) DEFAULT 0,
  `estimated_cost_usd` decimal(10,4) DEFAULT 0.0000,
  `last_active_at` datetime DEFAULT NULL,
  `archived_at` datetime DEFAULT NULL,
  `created_at` datetime DEFAULT current_timestamp(),
  `updated_at` datetime DEFAULT current_timestamp() ON UPDATE current_timestamp(),
  PRIMARY KEY (`id`),
  KEY `idx_ai_session_user` (`nx_user_id`,`role`),
  KEY `idx_ai_session_active` (`last_active_at`),
  KEY `idx_ai_session_archive` (`archived_at`)
) ENGINE=InnoDB AUTO_INCREMENT=31 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `tory_coach_flags`
--

DROP TABLE IF EXISTS `tory_coach_flags`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `tory_coach_flags` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `nx_user_id` bigint(20) NOT NULL,
  `coach_id` bigint(20) NOT NULL,
  `profile_id` int(11) DEFAULT NULL,
  `compat_signal` varchar(10) NOT NULL DEFAULT 'green',
  `compat_message` varchar(255) DEFAULT NULL,
  `warnings` longtext DEFAULT NULL,
  `learner_low_traits` longtext DEFAULT NULL,
  `learner_high_traits` longtext DEFAULT NULL,
  `created_at` datetime DEFAULT NULL,
  `updated_at` datetime DEFAULT NULL,
  `deleted_at` datetime DEFAULT NULL,
  PRIMARY KEY (`id`),
  KEY `idx_tory_flag_user` (`nx_user_id`),
  KEY `idx_tory_flag_coach` (`coach_id`),
  KEY `idx_tory_flag_signal` (`compat_signal`),
  KEY `idx_tory_flag_user_coach` (`nx_user_id`,`coach_id`)
) ENGINE=InnoDB AUTO_INCREMENT=6 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci ROW_FORMAT=DYNAMIC;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `tory_coach_overrides`
--

DROP TABLE IF EXISTS `tory_coach_overrides`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `tory_coach_overrides` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `roadmap_id` int(11) NOT NULL COMMENT 'FK → tory_roadmaps.id',
  `roadmap_item_id` int(11) DEFAULT NULL COMMENT 'FK → tory_roadmap_items.id (item affected)',
  `coach_id` bigint(20) NOT NULL COMMENT 'FK → coaches.id',
  `action` varchar(20) NOT NULL COMMENT 'reorder | swap | lock | unlock',
  `details` longtext DEFAULT NULL COMMENT 'JSON: {from_sequence, to_sequence} or {swapped_with_item_id} etc.',
  `reason` longtext DEFAULT NULL COMMENT 'Coach explanation for the override',
  `was_blocked` int(11) NOT NULL DEFAULT 0 COMMENT '1 = action was blocked by guardrail (tried to remove critical lesson)',
  `blocked_reason` longtext DEFAULT NULL COMMENT 'System message if action was blocked',
  `created_at` datetime DEFAULT NULL,
  `updated_at` datetime DEFAULT NULL,
  `deleted_at` datetime DEFAULT NULL,
  PRIMARY KEY (`id`),
  KEY `idx_tory_override_roadmap` (`roadmap_id`),
  KEY `idx_tory_override_coach` (`coach_id`),
  KEY `idx_tory_override_action` (`action`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci ROW_FORMAT=DYNAMIC;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `tory_content_tags`
--

DROP TABLE IF EXISTS `tory_content_tags`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `tory_content_tags` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `nx_lesson_id` int(11) NOT NULL COMMENT 'FK → nx_lessons.id',
  `lesson_detail_id` int(11) DEFAULT NULL COMMENT 'FK → lesson_details.id (optional granularity)',
  `trait_tags` longtext NOT NULL COMMENT 'JSON: [{trait, relevance_score, direction}]',
  `difficulty` int(11) DEFAULT NULL COMMENT 'Difficulty level 1-5',
  `learning_style` varchar(50) DEFAULT NULL COMMENT 'visual | reflective | active | theoretical | blended',
  `prerequisites` longtext DEFAULT NULL COMMENT 'JSON: prerequisite trait thresholds',
  `confidence` int(11) NOT NULL DEFAULT 0 COMMENT 'Confidence score 0-100',
  `review_status` varchar(20) NOT NULL DEFAULT 'pending' COMMENT 'pending | approved | rejected | needs_review',
  `pass1_tags` longtext DEFAULT NULL COMMENT 'JSON: First pass Claude Opus output',
  `pass2_tags` longtext DEFAULT NULL COMMENT 'JSON: Second pass Claude Opus output (different prompt)',
  `pass_agreement` int(11) DEFAULT NULL COMMENT 'Agreement score 0-100 between pass1 and pass2',
  `reviewed_by` int(11) DEFAULT NULL COMMENT 'FK → nx_users.id (coach/admin who reviewed)',
  `reviewed_at` datetime DEFAULT NULL,
  `review_notes` longtext DEFAULT NULL COMMENT 'Coach/admin notes on tag corrections',
  `created_at` datetime DEFAULT NULL,
  `updated_at` datetime DEFAULT NULL,
  `deleted_at` datetime DEFAULT NULL,
  `summary` text DEFAULT NULL,
  `learning_objectives` longtext DEFAULT NULL,
  `key_concepts` longtext DEFAULT NULL,
  `emotional_tone` varchar(50) DEFAULT NULL,
  `target_seniority` varchar(20) DEFAULT NULL,
  `estimated_minutes` int(11) DEFAULT NULL,
  `coaching_prompts` longtext DEFAULT NULL,
  `content_quality` longtext DEFAULT NULL,
  `pair_recommendations` longtext DEFAULT NULL,
  `slide_analysis` longtext DEFAULT NULL,
  `rag_chunk_ids` longtext DEFAULT NULL,
  `processed_at` datetime DEFAULT NULL,
  PRIMARY KEY (`id`),
  KEY `idx_tory_content_lesson` (`nx_lesson_id`),
  KEY `idx_tory_content_review` (`review_status`),
  KEY `idx_tory_content_confidence` (`confidence`),
  KEY `idx_tory_ct_eligible` (`deleted_at`,`review_status`,`confidence`,`nx_lesson_id`)
) ENGINE=InnoDB AUTO_INCREMENT=174 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci ROW_FORMAT=DYNAMIC;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `tory_feedback`
--

DROP TABLE IF EXISTS `tory_feedback`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `tory_feedback` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `nx_user_id` bigint(20) NOT NULL COMMENT 'FK → nx_users.id',
  `profile_id` int(11) DEFAULT NULL COMMENT 'FK → tory_learner_profiles.id',
  `type` varchar(30) NOT NULL COMMENT 'not_like_me | too_vague | incorrect_strength | other',
  `comment` longtext DEFAULT NULL COMMENT 'Optional learner comment',
  `profile_version` int(11) DEFAULT NULL COMMENT 'Version of profile when feedback was given',
  `resolved` int(11) NOT NULL DEFAULT 0 COMMENT '1 = feedback addressed in subsequent profile version',
  `resolved_at` datetime DEFAULT NULL,
  `created_at` datetime DEFAULT NULL,
  `updated_at` datetime DEFAULT NULL,
  `deleted_at` datetime DEFAULT NULL,
  PRIMARY KEY (`id`),
  KEY `idx_tory_feedback_user` (`nx_user_id`),
  KEY `idx_tory_feedback_profile` (`profile_id`),
  KEY `idx_tory_feedback_type` (`type`)
) ENGINE=InnoDB AUTO_INCREMENT=5 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci ROW_FORMAT=DYNAMIC;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `tory_learner_profiles`
--

DROP TABLE IF EXISTS `tory_learner_profiles`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `tory_learner_profiles` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `nx_user_id` bigint(20) NOT NULL COMMENT 'FK → nx_users.id',
  `onboarding_id` int(11) DEFAULT NULL COMMENT 'FK → nx_user_onboardings.id (source data)',
  `epp_summary` longtext NOT NULL COMMENT 'JSON: normalized 29-dimension EPP trait vector',
  `motivation_cluster` longtext NOT NULL COMMENT 'JSON: motivation drivers derived from Q&A',
  `strengths` longtext NOT NULL COMMENT 'JSON: top traits with scores',
  `gaps` longtext NOT NULL COMMENT 'JSON: growth areas with scores and motivation alignment',
  `learning_style` varchar(50) DEFAULT NULL COMMENT 'Inferred learning style preference',
  `profile_narrative` longtext DEFAULT NULL COMMENT 'Claude-generated human-readable profile summary (user-facing)',
  `confidence` int(11) NOT NULL DEFAULT 50 COMMENT 'Profile confidence 0-100 (grows with data)',
  `version` int(11) NOT NULL DEFAULT 1 COMMENT 'Profile version (increments on reassessment)',
  `source` varchar(30) NOT NULL DEFAULT 'epp_qa' COMMENT 'epp_qa | reassessment_mini | reassessment_full | discovery',
  `feedback_flags` int(11) NOT NULL DEFAULT 0 COMMENT 'Count of "doesnt sound like me" flags',
  `created_at` datetime DEFAULT NULL,
  `updated_at` datetime DEFAULT NULL,
  `deleted_at` datetime DEFAULT NULL,
  PRIMARY KEY (`id`),
  KEY `idx_tory_profile_user` (`nx_user_id`),
  KEY `idx_tory_profile_version` (`nx_user_id`,`version`),
  KEY `idx_tory_profile_active` (`nx_user_id`,`deleted_at`,`version`)
) ENGINE=InnoDB AUTO_INCREMENT=497 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci ROW_FORMAT=DYNAMIC;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `tory_notification_log`
--

DROP TABLE IF EXISTS `tory_notification_log`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `tory_notification_log` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `nx_user_id` bigint(20) NOT NULL,
  `notification_type` varchar(30) NOT NULL COMMENT 'path_generated|reassessment_change|coach_change|reassessment_reminder',
  `channel` varchar(10) NOT NULL COMMENT 'sms|email',
  `path_event_id` int(11) DEFAULT NULL COMMENT 'FK to tory_path_events.id (NULL for reminders)',
  `subject` varchar(255) DEFAULT NULL,
  `body` longtext DEFAULT NULL,
  `reason` longtext DEFAULT NULL COMMENT 'Copied from tory_path_events.reason',
  `status` varchar(20) NOT NULL DEFAULT 'pending' COMMENT 'pending|sent|failed|batched|skipped',
  `batched_until` datetime DEFAULT NULL COMMENT 'If status=batched, when it becomes eligible',
  `sent_at` datetime DEFAULT NULL,
  `error_detail` varchar(500) DEFAULT NULL,
  `created_at` datetime NOT NULL DEFAULT current_timestamp(),
  `updated_at` datetime NOT NULL DEFAULT current_timestamp() ON UPDATE current_timestamp(),
  `deleted_at` datetime DEFAULT NULL,
  PRIMARY KEY (`id`),
  KEY `idx_tory_notif_user` (`nx_user_id`),
  KEY `idx_tory_notif_type` (`notification_type`),
  KEY `idx_tory_notif_status` (`status`),
  KEY `idx_tory_notif_batch` (`nx_user_id`,`status`,`batched_until`),
  KEY `idx_tory_notif_user_sent` (`nx_user_id`,`sent_at`),
  KEY `idx_tory_notif_user_type_status` (`nx_user_id`,`notification_type`,`status`,`sent_at`)
) ENGINE=InnoDB AUTO_INCREMENT=56 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `tory_notification_optouts`
--

DROP TABLE IF EXISTS `tory_notification_optouts`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `tory_notification_optouts` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `nx_user_id` bigint(20) NOT NULL,
  `notification_type` varchar(30) NOT NULL COMMENT 'path_generated|reassessment_change|coach_change|reassessment_reminder|all',
  `opted_out` tinyint(1) NOT NULL DEFAULT 1,
  `opted_out_at` datetime DEFAULT NULL,
  `opted_in_at` datetime DEFAULT NULL COMMENT 'If user re-opts-in later',
  `created_at` datetime NOT NULL DEFAULT current_timestamp(),
  `updated_at` datetime NOT NULL DEFAULT current_timestamp() ON UPDATE current_timestamp(),
  `deleted_at` datetime DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `idx_tory_optout_user_type` (`nx_user_id`,`notification_type`),
  KEY `idx_tory_optout_user` (`nx_user_id`)
) ENGINE=InnoDB AUTO_INCREMENT=9 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `tory_path_events`
--

DROP TABLE IF EXISTS `tory_path_events`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `tory_path_events` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `nx_user_id` bigint(20) NOT NULL COMMENT 'FK -> nx_users.id (learner)',
  `coach_id` bigint(20) NOT NULL COMMENT 'FK -> coaches.id (coach who acted)',
  `event_type` varchar(20) NOT NULL COMMENT 'reordered | swapped | locked',
  `reason` longtext DEFAULT NULL COMMENT 'Coach reason text for the mutation',
  `details` longtext DEFAULT NULL COMMENT 'JSON: mutation-specific payload',
  `recommendation_ids` longtext DEFAULT NULL COMMENT 'JSON: list of tory_recommendations.id affected',
  `divergence_pct` int(11) DEFAULT NULL COMMENT 'Divergence percentage at time of event',
  `flagged_for_review` int(11) NOT NULL DEFAULT 0 COMMENT '1 = divergence >30%, flagged as coach insight',
  `created_at` datetime DEFAULT NULL,
  `updated_at` datetime DEFAULT NULL,
  `deleted_at` datetime DEFAULT NULL,
  PRIMARY KEY (`id`),
  KEY `idx_tory_pe_user` (`nx_user_id`),
  KEY `idx_tory_pe_coach` (`coach_id`),
  KEY `idx_tory_pe_type` (`event_type`),
  KEY `idx_tory_pe_user_type` (`nx_user_id`,`event_type`),
  KEY `idx_tory_pe_user_created` (`nx_user_id`,`deleted_at`,`created_at`)
) ENGINE=InnoDB AUTO_INCREMENT=39 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci ROW_FORMAT=DYNAMIC;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `tory_pedagogy_config`
--

DROP TABLE IF EXISTS `tory_pedagogy_config`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `tory_pedagogy_config` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `client_id` int(11) NOT NULL COMMENT 'FK → clients.id',
  `mode` varchar(20) NOT NULL DEFAULT 'balanced' COMMENT 'gap_fill | strength_lead | balanced',
  `gap_ratio` int(11) NOT NULL DEFAULT 50 COMMENT 'Percentage 0-100 for gap-filling emphasis',
  `strength_ratio` int(11) NOT NULL DEFAULT 50 COMMENT 'Percentage 0-100 for strength-leading emphasis',
  `configured_by` int(11) DEFAULT NULL COMMENT 'FK → nx_users.id or admin who set this',
  `configured_user_type` varchar(20) DEFAULT NULL COMMENT 'admin | coach | system',
  `created_at` datetime DEFAULT NULL,
  `updated_at` datetime DEFAULT NULL,
  `deleted_at` datetime DEFAULT NULL,
  PRIMARY KEY (`id`),
  KEY `idx_tory_pedagogy_client` (`client_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci ROW_FORMAT=DYNAMIC;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `tory_progress_snapshots`
--

DROP TABLE IF EXISTS `tory_progress_snapshots`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `tory_progress_snapshots` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `nx_user_id` bigint(20) NOT NULL COMMENT 'FK → nx_users.id',
  `roadmap_id` int(11) DEFAULT NULL COMMENT 'FK → tory_roadmaps.id (current roadmap at snapshot time)',
  `snapshot_date` date NOT NULL,
  `completion_pct` int(11) NOT NULL DEFAULT 0 COMMENT 'Roadmap completion 0-100',
  `engagement_score` int(11) DEFAULT NULL COMMENT 'Engagement score 0-100 (derived from backpack frequency, ratings, task completion)',
  `lessons_completed` int(11) NOT NULL DEFAULT 0,
  `lessons_total` int(11) NOT NULL DEFAULT 0,
  `days_active` int(11) DEFAULT NULL COMMENT 'Days with at least one interaction in this period',
  `days_stalled` int(11) DEFAULT NULL COMMENT 'Consecutive days with no activity',
  `path_changes` int(11) NOT NULL DEFAULT 0 COMMENT 'Number of roadmap adaptations to date',
  `coach_overrides` int(11) NOT NULL DEFAULT 0 COMMENT 'Number of coach interventions to date',
  `divergence_score` int(11) DEFAULT NULL COMMENT 'How much coach overrides diverge from Tory recs 0-100',
  `tory_accuracy` int(11) DEFAULT NULL COMMENT 'How well Tory predictions matched outcomes 0-100',
  `reassessments_completed` int(11) NOT NULL DEFAULT 0 COMMENT 'Total reassessments completed to date',
  `profile_confidence` int(11) DEFAULT NULL COMMENT 'Current profile confidence at snapshot time 0-100',
  `client_id` int(11) DEFAULT NULL COMMENT 'FK → clients.id (denormalized for dashboard queries)',
  `department_id` int(11) DEFAULT NULL COMMENT 'FK → departments.id (denormalized for team aggregates)',
  `created_at` datetime DEFAULT NULL,
  `updated_at` datetime DEFAULT NULL,
  `deleted_at` datetime DEFAULT NULL,
  PRIMARY KEY (`id`),
  KEY `idx_tory_snap_user` (`nx_user_id`),
  KEY `idx_tory_snap_date` (`snapshot_date`),
  KEY `idx_tory_snap_client` (`client_id`,`snapshot_date`),
  KEY `idx_tory_snap_dept` (`department_id`,`snapshot_date`),
  KEY `idx_tory_snap_user_date` (`nx_user_id`,`snapshot_date`),
  KEY `idx_tory_snap_aggregate` (`client_id`,`snapshot_date`,`completion_pct`,`engagement_score`)
) ENGINE=InnoDB AUTO_INCREMENT=3 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci ROW_FORMAT=DYNAMIC;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `tory_rag_chunks`
--

DROP TABLE IF EXISTS `tory_rag_chunks`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `tory_rag_chunks` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `lesson_detail_id` int(11) NOT NULL,
  `chunk_index` int(11) NOT NULL,
  `chunk_text` text NOT NULL,
  `chunk_type` varchar(50) DEFAULT NULL,
  `topic` varchar(200) DEFAULT NULL,
  `slide_ids` longtext DEFAULT NULL,
  `faiss_doc_id` varchar(100) DEFAULT NULL,
  `embedding_model` varchar(100) DEFAULT NULL,
  `created_at` datetime DEFAULT current_timestamp(),
  PRIMARY KEY (`id`),
  KEY `idx_rag_chunk_lesson` (`lesson_detail_id`),
  KEY `idx_rag_chunk_faiss` (`faiss_doc_id`)
) ENGINE=InnoDB AUTO_INCREMENT=281 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `tory_reassessments`
--

DROP TABLE IF EXISTS `tory_reassessments`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `tory_reassessments` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `nx_user_id` bigint(20) NOT NULL COMMENT 'FK → nx_users.id',
  `profile_id` int(11) DEFAULT NULL COMMENT 'FK → tory_learner_profiles.id (profile before reassessment)',
  `type` varchar(20) NOT NULL COMMENT 'mini | full_epp',
  `trigger_reason` varchar(30) NOT NULL COMMENT 'scheduled | progress_milestone | coach_initiated | drift_detected | learner_feedback',
  `status` varchar(20) NOT NULL DEFAULT 'pending' COMMENT 'pending | sent | in_progress | completed | expired | failed',
  `assessment_data` longtext DEFAULT NULL COMMENT 'JSON: questions + answers (for mini) or full EPP scores (for full_epp)',
  `previous_scores` longtext DEFAULT NULL COMMENT 'JSON: EPP/profile snapshot before this reassessment',
  `new_scores` longtext DEFAULT NULL COMMENT 'JSON: EPP/profile snapshot after this reassessment',
  `result_delta` longtext DEFAULT NULL COMMENT 'JSON: [{trait, old_score, new_score, change_pct}]',
  `drift_detected` int(11) NOT NULL DEFAULT 0 COMMENT '1 = significant profile drift triggered path adaptation',
  `path_action` varchar(30) DEFAULT NULL COMMENT 'none | minor_reorder | major_adaptation | full_regeneration',
  `criteria_order_id` longtext DEFAULT NULL COMMENT 'Criteria Corp order ID (for full_epp type)',
  `sent_at` datetime DEFAULT NULL,
  `completed_at` datetime DEFAULT NULL,
  `expires_at` datetime DEFAULT NULL COMMENT 'Deadline for completion before expiry',
  `created_at` datetime DEFAULT NULL,
  `updated_at` datetime DEFAULT NULL,
  `deleted_at` datetime DEFAULT NULL,
  PRIMARY KEY (`id`),
  KEY `idx_tory_reassess_user` (`nx_user_id`),
  KEY `idx_tory_reassess_type` (`type`),
  KEY `idx_tory_reassess_status` (`status`),
  KEY `idx_tory_reassess_schedule` (`nx_user_id`,`type`,`status`),
  KEY `idx_tory_reassess_completed` (`nx_user_id`,`status`,`deleted_at`,`completed_at`)
) ENGINE=InnoDB AUTO_INCREMENT=2 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci ROW_FORMAT=DYNAMIC;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `tory_recommendations`
--

DROP TABLE IF EXISTS `tory_recommendations`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `tory_recommendations` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `nx_user_id` bigint(20) NOT NULL,
  `profile_id` int(11) NOT NULL,
  `nx_lesson_id` int(11) NOT NULL,
  `content_tag_id` int(11) DEFAULT NULL,
  `nx_journey_detail_id` int(11) DEFAULT NULL,
  `match_score` decimal(8,4) NOT NULL DEFAULT 0.0000,
  `gap_contribution` decimal(8,4) DEFAULT NULL,
  `strength_contribution` decimal(8,4) DEFAULT NULL,
  `adjusted_score` decimal(8,4) DEFAULT NULL,
  `sequence` int(11) NOT NULL DEFAULT 0,
  `match_rationale` longtext DEFAULT NULL,
  `matching_traits` longtext DEFAULT NULL,
  `is_discovery` int(11) NOT NULL DEFAULT 0,
  `locked_by_coach` int(11) NOT NULL DEFAULT 0 COMMENT '1 = locked by coach, survives re-ranking',
  `source` varchar(10) NOT NULL DEFAULT 'tory' COMMENT 'tory = algorithm | coach = manually modified',
  `pedagogy_mode` varchar(20) DEFAULT NULL,
  `pedagogy_ratio` varchar(10) DEFAULT NULL,
  `confidence` int(11) DEFAULT NULL,
  `batch_id` varchar(50) DEFAULT NULL,
  `created_at` datetime DEFAULT NULL,
  `updated_at` datetime DEFAULT NULL,
  `deleted_at` datetime DEFAULT NULL,
  PRIMARY KEY (`id`),
  KEY `idx_tory_rec_user` (`nx_user_id`),
  KEY `idx_tory_rec_lesson` (`nx_lesson_id`),
  KEY `idx_tory_rec_score` (`nx_user_id`,`match_score`),
  KEY `idx_tory_rec_batch` (`batch_id`),
  KEY `idx_tory_rec_sequence` (`nx_user_id`,`sequence`),
  KEY `idx_tory_rec_locked` (`nx_user_id`,`locked_by_coach`),
  KEY `idx_tory_rec_active` (`nx_user_id`,`deleted_at`,`sequence`),
  KEY `idx_tory_rec_batch_active` (`batch_id`,`deleted_at`,`sequence`)
) ENGINE=InnoDB AUTO_INCREMENT=241 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci ROW_FORMAT=DYNAMIC;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `tory_roadmap_items`
--

DROP TABLE IF EXISTS `tory_roadmap_items`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `tory_roadmap_items` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `roadmap_id` int(11) NOT NULL COMMENT 'FK → tory_roadmaps.id',
  `nx_lesson_id` int(11) NOT NULL COMMENT 'FK → nx_lessons.id',
  `content_tag_id` int(11) DEFAULT NULL COMMENT 'FK → tory_content_tags.id (tag used for matching)',
  `sequence` int(11) NOT NULL COMMENT 'Order in the roadmap (1-based)',
  `status` varchar(20) NOT NULL DEFAULT 'pending' COMMENT 'pending | active | completed | skipped | locked',
  `is_critical` int(11) NOT NULL DEFAULT 0 COMMENT '1 = cannot be removed by coach (guardrail)',
  `is_discovery` int(11) NOT NULL DEFAULT 0 COMMENT '1 = part of discovery phase (first 3-5)',
  `match_score` int(11) DEFAULT NULL COMMENT 'Cosine similarity score 0-100',
  `match_rationale` longtext DEFAULT NULL COMMENT 'Claude-generated explanation: why this lesson for this learner (user-facing)',
  `trait_targets` longtext DEFAULT NULL COMMENT 'JSON: EPP traits this lesson targets [{trait, expected_impact}]',
  `started_at` datetime DEFAULT NULL,
  `completed_at` datetime DEFAULT NULL,
  `learner_rating` int(11) DEFAULT NULL COMMENT 'Learner rating of this lesson 1-5',
  `original_sequence` int(11) DEFAULT NULL COMMENT 'Original position before coach reorder (for divergence tracking)',
  `created_at` datetime DEFAULT NULL,
  `updated_at` datetime DEFAULT NULL,
  `deleted_at` datetime DEFAULT NULL,
  PRIMARY KEY (`id`),
  KEY `idx_tory_item_roadmap` (`roadmap_id`),
  KEY `idx_tory_item_lesson` (`nx_lesson_id`),
  KEY `idx_tory_item_sequence` (`roadmap_id`,`sequence`),
  KEY `idx_tory_item_status` (`status`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci ROW_FORMAT=DYNAMIC;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `tory_roadmaps`
--

DROP TABLE IF EXISTS `tory_roadmaps`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `tory_roadmaps` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `nx_user_id` bigint(20) NOT NULL COMMENT 'FK → nx_users.id',
  `profile_id` int(11) NOT NULL COMMENT 'FK → tory_learner_profiles.id (profile used to generate)',
  `pedagogy_mode` varchar(20) NOT NULL DEFAULT 'balanced' COMMENT 'gap_fill | strength_lead | balanced (snapshot from client config)',
  `pedagogy_ratio` varchar(10) DEFAULT NULL COMMENT 'e.g. 70/30 — snapshot of ratio used',
  `version` int(11) NOT NULL DEFAULT 1 COMMENT 'Roadmap version (increments on adaptation)',
  `status` varchar(20) NOT NULL DEFAULT 'discovery' COMMENT 'discovery | active | completed | paused | archived',
  `total_lessons` int(11) NOT NULL DEFAULT 0,
  `completed_lessons` int(11) NOT NULL DEFAULT 0,
  `completion_pct` int(11) NOT NULL DEFAULT 0 COMMENT '0-100',
  `generation_rationale` longtext DEFAULT NULL COMMENT 'Claude-generated explanation of overall path strategy (user-facing)',
  `trigger_source` varchar(30) NOT NULL DEFAULT 'onboarding' COMMENT 'onboarding | discovery_complete | reassessment | coach_request | drift',
  `is_current` int(11) NOT NULL DEFAULT 1 COMMENT '1 = active roadmap, 0 = historical version',
  `created_by` int(11) DEFAULT NULL COMMENT 'FK → nx_users.id or system',
  `created_user_type` varchar(20) DEFAULT NULL COMMENT 'system | coach | admin',
  `created_at` datetime DEFAULT NULL,
  `updated_at` datetime DEFAULT NULL,
  `deleted_at` datetime DEFAULT NULL,
  PRIMARY KEY (`id`),
  KEY `idx_tory_roadmap_user` (`nx_user_id`),
  KEY `idx_tory_roadmap_current` (`nx_user_id`,`is_current`),
  KEY `idx_tory_roadmap_status` (`status`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci ROW_FORMAT=DYNAMIC;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Temporary table structure for view `v_database_summary`
--

DROP TABLE IF EXISTS `v_database_summary`;
/*!50001 DROP VIEW IF EXISTS `v_database_summary`*/;
SET @saved_cs_client     = @@character_set_client;
SET character_set_client = utf8mb4;
/*!50001 CREATE VIEW `v_database_summary` AS SELECT
 1 AS `table_name`,
  1 AS `row_count`,
  1 AS `data_size_mb`,
  1 AS `index_size_mb`,
  1 AS `engine` */;
SET character_set_client = @saved_cs_client;

--
-- Table structure for table `video_libraries`
--

DROP TABLE IF EXISTS `video_libraries`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `video_libraries` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `nx_journey_detail_id` int(11) DEFAULT NULL,
  `nx_chapter_detail_id` int(11) DEFAULT NULL,
  `nx_lesson_id` int(11) DEFAULT NULL,
  `title` longtext DEFAULT NULL,
  `transcript` longtext DEFAULT NULL,
  `video` longtext DEFAULT NULL,
  `thumbnail` longtext DEFAULT NULL,
  `assets` longtext DEFAULT NULL,
  `job` longtext DEFAULT NULL,
  `locator` longtext DEFAULT NULL,
  `url` longtext DEFAULT NULL,
  `created_by` int(11) DEFAULT NULL,
  `created_user_type` varchar(20) DEFAULT NULL,
  `created_at` datetime DEFAULT NULL,
  `updated_at` datetime DEFAULT NULL,
  `deleted_at` datetime DEFAULT NULL,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=182 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Final view structure for view `v_database_summary`
--

/*!50001 DROP VIEW IF EXISTS `v_database_summary`*/;
/*!50001 SET @saved_cs_client          = @@character_set_client */;
/*!50001 SET @saved_cs_results         = @@character_set_results */;
/*!50001 SET @saved_col_connection     = @@collation_connection */;
/*!50001 SET character_set_client      = utf8mb3 */;
/*!50001 SET character_set_results     = utf8mb3 */;
/*!50001 SET collation_connection      = utf8mb3_general_ci */;
/*!50001 CREATE ALGORITHM=UNDEFINED */
/*!50013 DEFINER=`rahil`@`localhost` SQL SECURITY DEFINER */
/*!50001 VIEW `v_database_summary` AS select `information_schema`.`TABLES`.`TABLE_NAME` AS `table_name`,`information_schema`.`TABLES`.`TABLE_ROWS` AS `row_count`,round(`information_schema`.`TABLES`.`DATA_LENGTH` / 1048576,2) AS `data_size_mb`,round(`information_schema`.`TABLES`.`INDEX_LENGTH` / 1048576,2) AS `index_size_mb`,`information_schema`.`TABLES`.`ENGINE` AS `engine` from `information_schema`.`TABLES` where `information_schema`.`TABLES`.`TABLE_SCHEMA` = 'baap' and `information_schema`.`TABLES`.`TABLE_TYPE` = 'BASE TABLE' order by `information_schema`.`TABLES`.`TABLE_ROWS` desc */;
/*!50001 SET character_set_client      = @saved_cs_client */;
/*!50001 SET character_set_results     = @saved_cs_results */;
/*!50001 SET collation_connection      = @saved_col_connection */;
/*!40103 SET TIME_ZONE=@OLD_TIME_ZONE */;

/*!40101 SET SQL_MODE=@OLD_SQL_MODE */;
/*!40014 SET FOREIGN_KEY_CHECKS=@OLD_FOREIGN_KEY_CHECKS */;
/*!40014 SET UNIQUE_CHECKS=@OLD_UNIQUE_CHECKS */;
/*!40101 SET CHARACTER_SET_CLIENT=@OLD_CHARACTER_SET_CLIENT */;
/*!40101 SET CHARACTER_SET_RESULTS=@OLD_CHARACTER_SET_RESULTS */;
/*!40101 SET COLLATION_CONNECTION=@OLD_COLLATION_CONNECTION */;
/*!40111 SET SQL_NOTES=@OLD_SQL_NOTES */;

-- Dump completed on 2026-03-31 11:59:25
