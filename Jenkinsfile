pipeline {

  agent any

  stages {
	  stage('Conan configuration') {
      steps {
        rtConanClient (id: "myConanClient")
        rtConanRemote (
          name: "artifactory",
          serverId: "artifactory",
          repo: "conan-local",
          clientId: "myConanClient",
        )
      }
    }

    stage('Export recipies') {
      steps {
        rtBuildInfo(
          captureEnv: true,
          // Maximum builds to keep in Artifactory.
          maxBuilds: 5,
          // Maximum days to keep the builds in Artifactory.
          maxDays: 7,
          // Also delete the build artifacts when deleting a build.
          deleteBuildArtifacts: true,
        )
        rtConanRun(
          clientId: "myConanClient",
          command: "export semver"
        )
        rtConanRun(
          clientId: "myConanClient",
          command: "upload -r artifactory semver --all --confirm"
        )
        rtPublishBuildInfo (
          serverId: "artifactory"
        )
      }
    }
  }
}
